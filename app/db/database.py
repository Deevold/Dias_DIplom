from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DATABASE_URL, DEFAULT_ELO


def get_connection(database_url=DATABASE_URL):
    return psycopg2.connect(database_url)


def _format_timestamp(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _normalize_battle_row(row):
    if not row:
        return None

    normalized = dict(row)
    for key in ("started_at", "finished_at", "ready_started_at", "player_two_next_action_at"):
        normalized[key] = _format_timestamp(normalized.get(key))
    return normalized


def _normalize_battle_rows(rows):
    return [_normalize_battle_row(row) for row in rows]


def init_db(database_url=DATABASE_URL):
    conn = get_connection(database_url)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT,
            language TEXT NOT NULL DEFAULT 'ru',
            card_theme TEXT NOT NULL DEFAULT 'blue',
            elo INTEGER NOT NULL DEFAULT 1000,
            total_points INTEGER NOT NULL DEFAULT 0,
            battle_wins INTEGER NOT NULL DEFAULT 0,
            battle_losses INTEGER NOT NULL DEFAULT 0,
            battle_draws INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'ru'")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id SERIAL PRIMARY KEY,
            section TEXT NOT NULL,
            level TEXT NOT NULL,
            mode TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percent INTEGER NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS battles (
            id SERIAL PRIMARY KEY,
            battle_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            ranked BOOLEAN NOT NULL DEFAULT TRUE,
            player_one_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            player_two_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            player_one_ready BOOLEAN NOT NULL DEFAULT FALSE,
            player_two_ready BOOLEAN NOT NULL DEFAULT FALSE,
            ready_started_at TIMESTAMP,
            bot_level TEXT,
            player_one_score INTEGER NOT NULL DEFAULT 0,
            player_two_score INTEGER NOT NULL DEFAULT 0,
            player_one_lives INTEGER,
            player_two_lives INTEGER,
            player_one_answers TEXT NOT NULL DEFAULT '[]',
            player_two_answers TEXT NOT NULL DEFAULT '[]',
            player_one_times TEXT NOT NULL DEFAULT '[]',
            player_two_times TEXT NOT NULL DEFAULT '[]',
            player_two_next_action_at TIMESTAMP,
            tasks_json TEXT NOT NULL,
            winner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            winner_name TEXT,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            time_limit INTEGER NOT NULL DEFAULT 180
        )
        """
    )

    cursor.execute("ALTER TABLE battles ADD COLUMN IF NOT EXISTS player_one_ready BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE battles ADD COLUMN IF NOT EXISTS player_two_ready BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE battles ADD COLUMN IF NOT EXISTS ready_started_at TIMESTAMP")
    cursor.execute("ALTER TABLE battles ADD COLUMN IF NOT EXISTS player_two_next_action_at TIMESTAMP")

    conn.commit()
    conn.close()


def get_or_create_user(name, card_theme="blue"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, email, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        FROM users
        WHERE LOWER(name) = LOWER(%s)
        """,
        (name,),
    )
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE users SET card_theme = %s WHERE id = %s", (card_theme, row[0]))
        conn.commit()
        cursor.execute(
            """
            SELECT id, name, email, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
            FROM users
            WHERE id = %s
            """,
            (row[0],),
        )
        user = cursor.fetchone()
        conn.close()
        return user

    cursor.execute(
        """
        INSERT INTO users (name, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws)
        VALUES (%s, %s, %s, 0, 0, 0, 0)
        RETURNING id, name, email, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        """,
        (name, card_theme, DEFAULT_ELO),
    )
    user = cursor.fetchone()
    conn.commit()
    conn.close()
    return user


def create_user_account(name, email, password_hash, card_theme="blue"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, language, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws)
        VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, 0)
        RETURNING id, name, email, language, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        """,
        (name, email, password_hash, "ru", card_theme, DEFAULT_ELO),
    )
    user = cursor.fetchone()
    conn.commit()
    conn.close()
    return user


def create_user_account_with_language(name, email, password_hash, language="ru", card_theme="blue"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, language, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws)
        VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, 0)
        RETURNING id, name, email, language, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        """,
        (name, email, password_hash, language, card_theme, DEFAULT_ELO),
    )
    user = cursor.fetchone()
    conn.commit()
    conn.close()
    return user


def get_user_by_email(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, email, password_hash, language, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        FROM users
        WHERE LOWER(email) = LOWER(%s)
        """,
        (email,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, email, language, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_other_users(current_user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, email, card_theme, elo, total_points, battle_wins, battle_losses, battle_draws, created_at
        FROM users
        WHERE id != %s
        ORDER BY elo DESC, name ASC
        """,
        (current_user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_user_elo(user_id, new_elo):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET elo = %s WHERE id = %s", (new_elo, user_id))
    conn.commit()
    conn.close()


def add_user_points(user_id, points):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET total_points = total_points + %s
        WHERE id = %s
        """,
        (points, user_id),
    )
    conn.commit()
    conn.close()


def add_battle_result_to_user(user_id, result_type):
    conn = get_connection()
    cursor = conn.cursor()

    if result_type == "win":
        cursor.execute("UPDATE users SET battle_wins = battle_wins + 1 WHERE id = %s", (user_id,))
    elif result_type == "loss":
        cursor.execute("UPDATE users SET battle_losses = battle_losses + 1 WHERE id = %s", (user_id,))
    elif result_type == "draw":
        cursor.execute("UPDATE users SET battle_draws = battle_draws + 1 WHERE id = %s", (user_id,))

    conn.commit()
    conn.close()


def update_user_profile(user_id, name, card_theme):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET name = %s, card_theme = %s
        WHERE id = %s
        """,
        (name, card_theme, user_id),
    )
    conn.commit()
    conn.close()


def update_user_language(user_id, language):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET language = %s
        WHERE id = %s
        """,
        (language, user_id),
    )
    conn.commit()
    conn.close()


def save_result(section, level, mode, score, total, percent, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO results (section, level, mode, score, total, percent, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (section, level, mode, score, total, percent, user_id),
    )
    conn.commit()
    conn.close()


def get_all_results(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            ORDER BY created_at DESC
            """
        )
    else:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_best_result(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            ORDER BY percent DESC, score DESC
            LIMIT 1
            """
        )
    else:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE user_id = %s
            ORDER BY percent DESC, score DESC
            LIMIT 1
            """,
            (user_id,),
        )
    row = cursor.fetchone()
    conn.close()
    return row


def clear_all_results(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute("DELETE FROM results")
    else:
        cursor.execute("DELETE FROM results WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()


def get_results_by_section(section, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE section = %s
            ORDER BY created_at DESC
            """,
            (section,),
        )
    else:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE section = %s AND user_id = %s
            ORDER BY created_at DESC
            """,
            (section, user_id),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_total_attempts(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute("SELECT COUNT(*) FROM results")
    else:
        cursor.execute("SELECT COUNT(*) FROM results WHERE user_id = %s", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_average_percent(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute("SELECT AVG(percent) FROM results")
    else:
        cursor.execute("SELECT AVG(percent) FROM results WHERE user_id = %s", (user_id,))
    avg = cursor.fetchone()[0]
    conn.close()
    return round(float(avg), 2) if avg else 0


def get_best_result_by_section(section, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE section = %s
            ORDER BY percent DESC, score DESC
            LIMIT 1
            """,
            (section,),
        )
    else:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE section = %s AND user_id = %s
            ORDER BY percent DESC, score DESC
            LIMIT 1
            """,
            (section, user_id),
        )
    row = cursor.fetchone()
    conn.close()
    return row


def get_best_result_by_section_and_level(section, level, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE section = %s AND level = %s
            ORDER BY percent DESC, score DESC
            LIMIT 1
            """,
            (section, level),
        )
    else:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE section = %s AND level = %s AND user_id = %s
            ORDER BY percent DESC, score DESC
            LIMIT 1
            """,
            (section, level, user_id),
        )
    row = cursor.fetchone()
    conn.close()
    return row


def get_attempts_count_by_section(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT section, COUNT(*)
            FROM results
            GROUP BY section
            """
        )
    else:
        cursor.execute(
            """
            SELECT section, COUNT(*)
            FROM results
            WHERE user_id = %s
            GROUP BY section
            """,
            (user_id,),
        )
    rows = cursor.fetchall()
    conn.close()
    result = {"math": 0, "logic": 0}
    for section, count in rows:
        result[section] = count
    return result


def get_attempts_count_by_level(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT level, COUNT(*)
            FROM results
            GROUP BY level
            """
        )
    else:
        cursor.execute(
            """
            SELECT level, COUNT(*)
            FROM results
            WHERE user_id = %s
            GROUP BY level
            """,
            (user_id,),
        )
    rows = cursor.fetchall()
    conn.close()
    result = {"easy": 0, "medium": 0, "hard": 0}
    for level, count in rows:
        result[level] = count
    return result


def get_last_results(limit=5, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    else:
        cursor.execute(
            """
            SELECT id, section, level, mode, score, total, percent, created_at
            FROM results
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_favorite_section(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT section, COUNT(*) as total_count
        FROM results
        WHERE user_id = %s
        GROUP BY section
        ORDER BY total_count DESC, section ASC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def create_battle(
    battle_type,
    ranked,
    player_one_id,
    tasks_json,
    time_limit,
    status="active",
    player_two_id=None,
    player_one_ready=False,
    player_two_ready=False,
    bot_level=None,
    player_one_lives=None,
    player_two_lives=None,
    player_two_next_action_at=None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO battles (
            battle_type, status, ranked, player_one_id, player_two_id, bot_level,
            player_one_ready, player_two_ready, player_one_lives, player_two_lives, player_two_next_action_at, tasks_json, time_limit
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            battle_type,
            status,
            ranked,
            player_one_id,
            player_two_id,
            bot_level,
            player_one_ready,
            player_two_ready,
            player_one_lives,
            player_two_lives,
            player_two_next_action_at,
            tasks_json,
            time_limit,
        ),
    )
    battle_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return battle_id


def get_battle_by_id(battle_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM battles WHERE id = %s", (battle_id,))
    row = cursor.fetchone()
    conn.close()
    return _normalize_battle_row(row)


def update_battle_state(
    battle_id,
    player_one_score,
    player_two_score,
    player_one_answers,
    player_two_answers,
    player_one_times,
    player_two_times,
    player_one_lives=None,
    player_two_lives=None,
    player_two_next_action_at=None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE battles
        SET player_one_score = %s,
            player_two_score = %s,
            player_one_answers = %s,
            player_two_answers = %s,
            player_one_times = %s,
            player_two_times = %s,
            player_one_lives = %s,
            player_two_lives = %s,
            player_two_next_action_at = COALESCE(%s, player_two_next_action_at)
        WHERE id = %s
        """,
        (
            player_one_score,
            player_two_score,
            player_one_answers,
            player_two_answers,
            player_one_times,
            player_two_times,
            player_one_lives,
            player_two_lives,
            player_two_next_action_at,
            battle_id,
        ),
    )
    conn.commit()
    conn.close()


def update_battle_tasks(battle_id, tasks_json):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE battles
        SET tasks_json = %s
        WHERE id = %s
        """,
        (tasks_json, battle_id),
    )
    conn.commit()
    conn.close()


def finish_battle(battle_id, winner_id, winner_name, status="finished"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE battles
        SET status = %s,
            winner_id = %s,
            winner_name = %s,
            finished_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (status, winner_id, winner_name, battle_id),
    )
    conn.commit()
    conn.close()


def get_active_battles_for_user(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """
        SELECT *
        FROM battles
        WHERE status IN ('active', 'waiting', 'ready_check')
          AND (player_one_id = %s OR player_two_id = %s)
        ORDER BY started_at DESC
        """,
        (user_id, user_id),
    )
    rows = cursor.fetchall()
    conn.close()
    return _normalize_battle_rows(rows)


def get_recent_battles_for_user(user_id, limit=5):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """
        SELECT *
        FROM battles
        WHERE status NOT IN ('active', 'waiting', 'ready_check')
          AND (player_one_id = %s OR player_two_id = %s)
        ORDER BY COALESCE(finished_at, started_at) DESC
        LIMIT %s
        """,
        (user_id, user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return _normalize_battle_rows(rows)


def get_finished_pvp_battles_for_user(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """
        SELECT *
        FROM battles
        WHERE battle_type = 'pvp'
          AND status NOT IN ('active', 'waiting', 'ready_check')
          AND (player_one_id = %s OR player_two_id = %s)
        ORDER BY COALESCE(finished_at, started_at) DESC
        """,
        (user_id, user_id),
    )
    rows = cursor.fetchall()
    conn.close()
    return _normalize_battle_rows(rows)


def get_user_open_pvp_battle(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """
        SELECT *
        FROM battles
        WHERE battle_type = 'pvp'
          AND status IN ('waiting', 'ready_check', 'active')
          AND (player_one_id = %s OR player_two_id = %s)
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (user_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()
    return _normalize_battle_row(row)


def cancel_waiting_pvp_battle(battle_id, player_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            DELETE FROM battles
            WHERE id = %s
              AND battle_type = 'pvp'
              AND status = 'waiting'
              AND player_one_id = %s
              AND player_two_id IS NULL
            RETURNING id
            """,
            (battle_id, player_id),
        )
        row = cursor.fetchone()
        if row:
            conn.commit()
            return row[0]

        cursor.execute(
            """
            DELETE FROM battles
            WHERE id = %s
              AND battle_type = 'pvp'
              AND status = 'ready_check'
              AND (player_one_id = %s OR player_two_id = %s)
            RETURNING id
            """,
            (battle_id, player_id, player_id),
        )
        row = cursor.fetchone()
        conn.commit()
        return row[0] if row else None
    finally:
        conn.close()


def join_or_create_pvp_battle(player_id, tasks_json, time_limit):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT battles.id
            FROM battles
            JOIN users ON users.id = battles.player_one_id
            WHERE battle_type = 'pvp'
              AND status = 'waiting'
              AND player_one_id != %s
              AND player_two_id IS NULL
            ORDER BY
              CASE
                WHEN ABS(users.elo - (SELECT elo FROM users WHERE id = %s)) <= 100 THEN 0
                WHEN ABS(users.elo - (SELECT elo FROM users WHERE id = %s)) <= 250 THEN 1
                ELSE 2
              END,
              ABS(users.elo - (SELECT elo FROM users WHERE id = %s)) ASC,
              started_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """,
            (player_id, player_id, player_id, player_id),
        )
        waiting_row = cursor.fetchone()

        if waiting_row:
            cursor.execute(
                """
                UPDATE battles
                SET status = 'ready_check',
                    player_two_id = %s,
                    player_one_ready = FALSE,
                    player_two_ready = FALSE,
                    ready_started_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id
                """,
                (player_id, waiting_row["id"]),
            )
            battle_id = cursor.fetchone()["id"]
        else:
            cursor.execute(
                """
                INSERT INTO battles (
                    battle_type, status, ranked, player_one_id, player_one_ready, player_two_ready, tasks_json, time_limit
                )
                VALUES ('pvp', 'waiting', TRUE, %s, FALSE, FALSE, %s, %s)
                RETURNING id
                """,
                (player_id, tasks_json, time_limit),
            )
            battle_id = cursor.fetchone()["id"]

        conn.commit()
        return battle_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_battle_ready_state(battle_id, player_side, is_ready):
    if player_side not in ("player_one", "player_two"):
        return None

    field_name = "player_one_ready" if player_side == "player_one" else "player_two_ready"
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            f"""
            UPDATE battles
            SET {field_name} = %s
            WHERE id = %s
            RETURNING *
            """,
            (is_ready, battle_id),
        )
        row = cursor.fetchone()
        conn.commit()
        return _normalize_battle_row(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def try_activate_ready_battle(battle_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            UPDATE battles
            SET status = 'active',
                started_at = CURRENT_TIMESTAMP,
                ready_started_at = NULL
            WHERE id = %s
              AND status = 'ready_check'
              AND player_one_id IS NOT NULL
              AND player_two_id IS NOT NULL
              AND player_one_ready = TRUE
              AND player_two_ready = TRUE
            RETURNING *
            """,
            (battle_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        return _normalize_battle_row(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_all_app_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE battles, results, users RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


def delete_battle(battle_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM battles WHERE id = %s", (battle_id,))
    conn.commit()
    conn.close()
