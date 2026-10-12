"""Texas property tax protest helper: Flask app factory and dev server.

Dev server:  python -m app.main            (http://127.0.0.1:5000)
Env vars:    HOST (default 127.0.0.1), PORT (default 5000), FLASK_DEBUG=1
Production:  gunicorn app.wsgi:app
"""
import os

from flask import Flask, send_from_directory

from app.config import load_counties
from app.routes.api import bp as api_bp

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app(counties=None):
    """`counties` is {id: settings} as from load_counties(); default reads config.yaml."""
    app = Flask(__name__, static_folder=STATIC, static_url_path="/static")
    app.config["COUNTIES"] = counties if counties is not None else load_counties()
    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    return app


if __name__ == "__main__":
    create_app().run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
