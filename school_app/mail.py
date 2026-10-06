"""Отправка ссылки восстановления по SMTP с шифрованием."""
import smtplib
import ssl
from email.message import EmailMessage


def send_reset_email(config, recipient, link):
    message = EmailMessage()
    message['Subject'] = f"{config['BRAND']} — восстановление пароля"
    message['From'] = config['MAIL_FROM']
    message['To'] = recipient
    message.set_content(
        f"Чтобы установить новый пароль, перейдите по ссылке:\n{link}\n\n"
        "Ссылка действует 30 минут и только один раз.\n"
        "Если вы не запрашивали смену пароля, просто проигнорируйте письмо."
    )
    context = ssl.create_default_context()
    port = config['SMTP_PORT']
    client = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    kwargs = {'context': context} if port == 465 else {}
    with client(config['SMTP_HOST'], port, timeout=20, **kwargs) as smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
        smtp.send_message(message)
