"""Пульс — школьный проект на Flask без JavaScript."""
import os
from waitress import serve
from school_app.web import create_app

app = create_app('pulse')

if __name__ == '__main__':
    serve(app, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '5001')))
