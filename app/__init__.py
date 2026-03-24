from flask import Flask

from app.db.database import init_db
from app.routes import register_routes


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object("config")

    init_db(app.config["DATABASE_URL"])
    register_routes(app)

    return app
