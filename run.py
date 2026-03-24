from app import create_app
from config import DEBUG, FLASK_HOST, FLASK_PORT


app = create_app()


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=DEBUG)
