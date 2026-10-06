"""Развитие заготовки учителя: Flask, /, /login и /user_register.

Вместо jQuery формы отправляют обычный POST. Все проверки делает Python.
"""
import hashlib
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from dotenv import dotenv_values
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from school_app import ai_client
from school_app.database import get_db, init_db
from school_app.mail import send_reset_email

THEMES = {
    'orbit': {'BRAND': 'Орбита', 'TAGLINE': 'Большие идеи начинаются с вопроса.',
              'DESCRIPTION': 'Твой помощник в мире знаний. Разбирай сложное, находи идеи и изучай новое вместе с нейросетью.'},
    'pulse': {'BRAND': 'Пульс', 'TAGLINE': 'Дай своим идеям новый импульс.',
              'DESCRIPTION': 'Пространство для любопытства. Задавай вопросы, исследуй темы и находи свой следующий шаг.'},
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def create_app(theme='orbit', config=None):
    root = Path(__file__).resolve().parent
    instance = Path((config or {}).get('INSTANCE_PATH', root.parent / f'version_{theme}' / 'instance'))
    instance.mkdir(parents=True, exist_ok=True)
    settings = {**dotenv_values(root.parent / f'version_{theme}' / '.env'), **os.environ}
    secret = settings.get('SECRET_KEY')
    if not secret:
        secret_file = instance / 'session.key'
        try:
            with secret_file.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = secret_file.read_text(encoding='utf-8')
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.update(
        SECRET_KEY=secret, DATABASE=str(instance / 'site.sqlite3'), THEME=theme,
        MAX_CONTENT_LENGTH=32 * 1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_NAME=f'{theme}_session',
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=settings.get('COOKIE_SECURE') == '1',
        GATEWAY_URL=settings.get('GATEWAY_URL', ''), DEMO_TOKEN=settings.get('DEMO_TOKEN', ''),
        PUBLIC_URL=settings.get('PUBLIC_URL', 'http://127.0.0.1:5000' if theme == 'orbit' else 'http://127.0.0.1:5001'),
        SMTP_HOST=settings.get('SMTP_HOST', ''), SMTP_PORT=int(settings.get('SMTP_PORT') or '465'),
        SMTP_USERNAME=settings.get('SMTP_USERNAME', ''), SMTP_PASSWORD=settings.get('SMTP_PASSWORD', ''),
        MAIL_FROM=settings.get('MAIL_FROM', ''), **THEMES[theme],
    )
    if config:
        app.config.update(config)
    init_db(app)

    def limited(key, maximum=10, seconds=900):
        db = get_db()
        now = time.time()
        with db:
            db.execute('DELETE FROM rate_limits WHERE started_at < ?', (now - seconds,))
            db.execute('INSERT INTO rate_limits VALUES (?, ?, 1) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1', (key, now))
        return db.execute('SELECT attempts FROM rate_limits WHERE key=?', (key,)).fetchone()[0] > maximum

    @app.before_request
    def protect_forms():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        if request.method == 'POST' and not secrets.compare_digest(session['csrf'].encode(), request.form.get('csrf', '').encode()):
            abort(400, description='Форма устарела. Обновите страницу и повторите действие.')
        g.user = None
        if 'user_id' in session:
            user = get_db().execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
            if user and user['session_version'] == session.get('session_version'):
                g.user = user

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def template_context():
        return {'brand': app.config['BRAND'], 'theme': theme,
                'tagline': app.config['TAGLINE'], 'description': app.config['DESCRIPTION']}

    def smtp_ready():
        return all(app.config[key] for key in ['SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'MAIL_FROM'])

    def auth_page(mode, status=200):
        return render_template('auth.html', mode=mode, smtp_ready=smtp_ready()), status

    def password_error():
        password = request.form.get('password', '')
        if not 8 <= len(password) <= 128:
            return 'Пароль должен содержать от 8 до 128 символов.'
        if password != request.form.get('confirm_password', ''):
            return 'Пароли не совпадают.'
        return None

    @app.get('/')
    def registration():
        if g.user:
            return redirect(url_for('chat'))
        return auth_page('register')

    @app.post('/user_register')
    def user_register():
        if limited('register:' + (request.remote_addr or ''), 20):
            abort(429)
        name = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        error = password_error()
        if not 2 <= len(name) <= 60:
            error = 'Введите имя длиной от 2 до 60 символов.'
        if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            error = 'Введите корректный адрес электронной почты.'
        if error:
            flash(error, 'error')
            return auth_page('register', 400)
        code = secrets.token_hex(12).upper()
        code = '-'.join(code[i:i+6] for i in range(0, len(code), 6))
        db = get_db()
        try:
            with db:
                cursor = db.execute('INSERT INTO users(username,email,password_hash,recovery_hash) VALUES (?,?,?,?)',
                    (name, email, generate_password_hash(request.form['password'], method='scrypt'), digest(code)))
        except sqlite3.IntegrityError:
            flash('Этот адрес уже зарегистрирован. Войдите или восстановите пароль.', 'error')
            return auth_page('register', 400)
        session.clear()
        session.update(user_id=cursor.lastrowid, session_version=1, csrf=secrets.token_urlsafe(32))
        return render_template('recovery_code.html', code=code)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            if limited('login:' + (request.remote_addr or ''), 20):
                abort(429)
            user = get_db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if user and check_password_hash(user['password_hash'], request.form.get('password', '')):
                session.clear()
                session.update(user_id=user['id'], session_version=user['session_version'], csrf=secrets.token_urlsafe(32))
                return redirect(url_for('chat'))
            flash('Почта или пароль указаны неверно.', 'error')
            return auth_page('login', 400)
        return auth_page('login')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            if not smtp_ready():
                flash('Отправка писем ещё не настроена. Используйте резервный код.', 'error')
                return auth_page('forgot', 503)
            if limited('reset:' + (request.remote_addr or ''), 5):
                abort(429)
            email = request.form.get('email', '').strip().lower()
            db = get_db()
            user = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if user:
                token = secrets.token_urlsafe(32)
                with db:
                    db.execute('DELETE FROM password_resets WHERE user_id=? OR expires_at < ?', (user['id'], time.time()))
                    db.execute('INSERT INTO password_resets VALUES (?,?,?)', (digest(token), user['id'], time.time() + 1800))
                link = app.config['PUBLIC_URL'].rstrip('/') + url_for('reset_password', token=token)
                try:
                    send_reset_email(app.config, email, link)
                except Exception:
                    # Не выводим адрес, ссылку, пароль SMTP или текст исключения в журнал.
                    app.logger.warning('Не удалось доставить письмо восстановления.')
                    with db:
                        db.execute('DELETE FROM password_resets WHERE token_hash=?', (digest(token),))
            flash('Если аккаунт существует, мы отправили ссылку на почту. Если письмо не пришло, используйте резервный код.', 'success')
            return redirect(url_for('forgot_password'))
        return auth_page('forgot')

    @app.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        db = get_db()
        record = db.execute('SELECT * FROM password_resets WHERE token_hash=? AND expires_at>?', (digest(token), time.time())).fetchone()
        if not record:
            flash('Ссылка недействительна или срок её действия истёк.', 'error')
            return redirect(url_for('forgot_password'))
        if request.method == 'POST':
            error = password_error()
            if error:
                flash(error, 'error')
                return auth_page('reset', 400)
            with db:
                # Проверяем одноразовость внутри транзакции, в том числе при одновременных запросах.
                db.execute('BEGIN IMMEDIATE')
                valid = db.execute('SELECT user_id FROM password_resets WHERE token_hash=? AND expires_at>?', (digest(token), time.time())).fetchone()
                if not valid:
                    abort(400)
                db.execute('UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?',
                           (generate_password_hash(request.form['password'], method='scrypt'), valid['user_id']))
                db.execute('DELETE FROM password_resets WHERE user_id=?', (valid['user_id'],))
            session.clear()
            flash('Пароль изменён. Войдите с новым паролем.', 'success')
            return redirect(url_for('login'))
        return auth_page('reset')

    @app.route('/recover', methods=['GET', 'POST'])
    def recover():
        if request.method == 'POST':
            if limited('recovery:' + (request.remote_addr or ''), 10):
                abort(429)
            error = password_error()
            if error:
                flash(error, 'error')
                return auth_page('recover', 400)
            db = get_db()
            email = request.form.get('email', '').strip().lower()
            old_hash = digest(request.form.get('recovery_code', '').strip().upper())
            new_code = secrets.token_hex(12).upper()
            new_code = '-'.join(new_code[i:i+6] for i in range(0, len(new_code), 6))
            with db:
                cursor = db.execute('UPDATE users SET password_hash=?, recovery_hash=?, session_version=session_version+1 WHERE email=? AND recovery_hash=?',
                    (generate_password_hash(request.form['password'], method='scrypt'), digest(new_code), email, old_hash))
                if cursor.rowcount:
                    db.execute('DELETE FROM password_resets WHERE user_id=(SELECT id FROM users WHERE email=?)', (email,))
            if not cursor.rowcount:
                flash('Неверная почта или резервный код.', 'error')
                return auth_page('recover', 400)
            session.clear()
            session['csrf'] = secrets.token_urlsafe(32)
            return render_template('recovery_code.html', code=new_code, recovered=True)
        return auth_page('recover')

    @app.route('/chat', methods=['GET', 'POST'])
    def chat():
        if not g.user:
            return redirect(url_for('login'))
        if request.method == 'POST':
            prompt = request.form.get('prompt', '').strip()
            form_id = request.form.get('request_id', '')
            if not form_id or form_id != session.get('chat_request_id'):
                flash('Этот вопрос уже отправлен. Напишите новый.', 'error')
                return redirect(url_for('chat'))
            if not 1 <= len(prompt) <= 2000:
                flash('Введите вопрос длиной от 1 до 2000 символов.', 'error')
                return redirect(url_for('chat'))
            session.pop('chat_request_id', None)
            try:
                answer = ai_client.ask(app.config, prompt, form_id)
                with get_db() as db:
                    db.execute('INSERT INTO messages(user_id,prompt,answer) VALUES (?,?,?)', (g.user['id'], prompt, answer))
            except ai_client.AIError as exc:
                flash(str(exc), 'error')
            return redirect(url_for('chat'))
        remaining, unavailable = None, None
        try:
            remaining = ai_client.quota(app.config)
        except ai_client.AIError as exc:
            unavailable = str(exc)
        session['chat_request_id'] = secrets.token_hex(16)
        messages = get_db().execute('SELECT * FROM messages WHERE user_id=? ORDER BY id', (g.user['id'],)).fetchall()
        return render_template('chat.html', messages=messages, remaining=remaining, unavailable=unavailable)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error_page(error):
        descriptions = {400: 'Обновите страницу и попробуйте ещё раз.', 404: 'Такой страницы нет.',
                        413: 'Отправленная форма слишком большая.', 429: 'Слишком много попыток. Попробуйте через 15 минут.'}
        return render_template('error.html', code=error.code, message=descriptions[error.code]), error.code

    return app
