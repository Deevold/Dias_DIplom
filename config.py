import os


def load_local_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env()


SECRET_KEY = os.getenv("SECRET_KEY", "logic_app_secret_key_123")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345678@localhost:5432/dias_db")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
TASKS_COUNT = 10
TIME_LIMITS = {
    "easy": 120,
    "medium": 180,
    "hard": 240,
}
PLAYER_THEMES = {
    "blue": "Синий",
    "green": "Зеленый",
    "orange": "Оранжевый",
    "crimson": "Малиновый",
    "teal": "Бирюзовый",
    "gold": "Золотой",
}
BATTLE_TIME_LIMIT = 180
BOT_BATTLE_TASKS_COUNT = 12
PVP_BATTLE_TASKS_COUNT = 18
BATTLE_QUESTION_TIME = 20
BATTLE_POINTS_POSSIBLE = 1000
DEFAULT_ELO = 1000
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BOT_LEVELS = {
    "easy": {"name": "AI Easy", "accuracy": 0.58, "min_time": 7, "max_time": 14},
    "medium": {"name": "AI Medium", "accuracy": 0.8, "min_time": 4, "max_time": 9},
    "hard": {"name": "AI Hard", "accuracy": 0.93, "min_time": 2, "max_time": 5},
}
