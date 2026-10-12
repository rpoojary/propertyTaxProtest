"""WSGI entry point: gunicorn app.wsgi:app"""
from app.main import create_app

app = create_app()
