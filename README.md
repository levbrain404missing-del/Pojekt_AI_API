# Пульс — школьный ИИ-помощник

Учебный сайт на Python и Flask, созданный по заготовке учителя. JavaScript не используется: формы отправляются обычными POST-запросами, а всю логику выполняет Python.

## Возможности

- регистрация по имени и email;
- хеширование паролей алгоритмом scrypt;
- вход и выход;
- восстановление по письму или резервному коду;
- вопросы к Mistral AI и личная история;
- общий серверный лимит: четыре обращения до ручного сброса владельцем;
- адаптивный дизайн «Пульс».

## Локальный запуск

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe app.py
```

После заполнения `.env` откройте http://127.0.0.1:5001.

## Развёртывание

Команда запуска: `python app.py`. Хостинг должен поддерживать Python и постоянный диск для SQLite. Переменные из `.env.example` задаются в закрытых настройках хостинга. Настоящий `MISTRAL_API_KEY` хранится только на отдельном сервере владельца и в этот репозиторий не добавляется.

GitHub хранит код, но не запускает Flask как сервер. Для чата требуется доступный по HTTPS `GATEWAY_URL`.

## Структура

- `app.py` — запуск версии «Пульс»;
- `school_app/web.py` — регистрация, вход, восстановление и чат;
- `school_app/database.py` — таблицы SQLite;
- `school_app/ai_client.py` — обращение к серверу владельца;
- `school_app/templates` — HTML без JavaScript;
- `school_app/static` — оформление.

Репозиторий: https://github.com/levbrain404missing-del/Pojekt_AI_API

