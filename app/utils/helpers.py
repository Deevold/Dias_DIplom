from datetime import datetime, timedelta


def format_datetime(dt_str):
    if isinstance(dt_str, datetime):
        dt = dt_str
    else:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    dt = dt + timedelta(hours=5)
    return dt.strftime("%d.%m.%Y %H:%M")


def get_time_limit(level, time_limits):
    return time_limits.get(level, 180)


def get_remaining_seconds(session, time_limits):
    started_at = session.get("started_at")
    level = session.get("level")

    if not started_at or not level:
        return None

    started_dt = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
    elapsed = int((datetime.now() - started_dt).total_seconds())
    remaining = get_time_limit(level, time_limits) - elapsed
    return max(0, remaining)


def get_elapsed_seconds(session):
    started_at = session.get("started_at")

    if not started_at:
        return 0

    started_dt = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
    elapsed = int((datetime.now() - started_dt).total_seconds())
    return max(0, elapsed)


def format_seconds(seconds):
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def clear_game_session(session):
    for key in (
        "level",
        "mode",
        "tasks",
        "current",
        "user_answers",
        "result_saved",
        "started_at",
        "time_limit",
        "time_expired",
        "training_mode",
    ):
        session.pop(key, None)
