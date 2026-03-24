import os
from datetime import datetime, timedelta

from flask import jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.db.database import (
    add_battle_result_to_user,
    add_user_points,
    cancel_waiting_pvp_battle,
    clear_all_app_data,
    clear_all_results,
    create_user_account_with_language,
    create_battle,
    delete_battle,
    finish_battle,
    get_active_battles_for_user,
    get_all_results,
    get_all_users_for_leaderboard,
    get_attempts_count_by_level,
    get_attempts_count_by_section,
    get_average_percent,
    get_battle_by_id,
    get_best_result,
    get_best_result_by_section_and_level,
    get_finished_pvp_battles_for_user,
    get_favorite_section,
    get_last_results,
    get_recent_battles_for_user,
    get_results_by_section,
    get_total_attempts,
    get_user_by_email,
    get_user_by_id,
    get_user_open_pvp_battle,
    join_or_create_pvp_battle,
    save_result,
    set_battle_ready_state,
    try_activate_ready_battle,
    update_battle_state,
    update_battle_tasks,
    update_user_elo,
    update_user_language,
    update_user_profile,
)
from app.services.battle_service import (
    calculate_answer_score,
    calculate_elo_change,
    calculate_progress,
    dumps_data,
    generate_battle_tasks,
    get_battle_deadline_timestamp,
    get_battle_remaining_seconds,
    get_bot_level_config,
    get_current_battle_question,
    is_pushout,
    loads_data,
)
from app.services.gemini_service import get_gemini_answer_data, pick_ai_delay
from app.services.logic_service import generate_logic_tasks
from app.services.math_service import generate_math_tasks
from app.services.stats_service import format_best_row, format_result_row
from app.utils.helpers import (
    clear_game_session,
    format_datetime,
    format_seconds,
    get_elapsed_seconds,
    get_remaining_seconds,
    get_time_limit,
)
from app.utils.i18n import (
    DRAW_MARKER,
    LANGUAGE_OPTIONS,
    is_draw_value,
    normalize_language,
    translate,
    translate_bot_level,
    translate_level,
    translate_mode,
    translate_section,
    translate_theme,
)


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    row = get_user_by_id(user_id)
    if not row:
        session.pop("user_id", None)
        session.pop("user_name", None)
        session.pop("card_theme", None)
        return None

    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "language": normalize_language(row[3]),
        "card_theme": row[4],
        "elo": row[5],
        "total_points": row[6],
        "battle_wins": row[7],
        "battle_losses": row[8],
        "battle_draws": row[9],
        "created_at": format_datetime(row[10]),
    }


def require_current_user():
    return get_current_user()


def format_user_card(row):
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "language": normalize_language(row[3]),
        "card_theme": row[4],
        "elo": row[5],
        "total_points": row[6],
        "battle_wins": row[7],
        "battle_losses": row[8],
        "battle_draws": row[9],
        "created_at": format_datetime(row[10]),
    }


def get_current_language(current_user=None):
    session_language = session.get("lang")
    if session_language in LANGUAGE_OPTIONS:
        return session_language
    if current_user and current_user.get("language"):
        return normalize_language(current_user["language"])
    return "ru"


def t(key, **kwargs):
    return translate(key, get_current_language(get_current_user()), **kwargs)


def get_battle_opponent(battle, current_user):
    if battle["battle_type"] == "bot":
        bot_level = battle["bot_level"]
        return {
            "id": None,
            "name": translate_bot_level(bot_level, get_current_language(current_user)),
            "elo": None,
            "card_theme": "orange",
        }

    opponent_id = battle["player_two_id"] if battle["player_one_id"] == current_user["id"] else battle["player_one_id"]
    row = get_user_by_id(opponent_id)
    return format_user_card(row) if row else None


def get_player_side(battle, current_user_id):
    if battle["player_one_id"] == current_user_id:
        return "player_one"
    if battle["player_two_id"] == current_user_id:
        return "player_two"
    return None


def get_battle_view_state(battle, current_user):
    side = get_player_side(battle, current_user["id"])
    opponent = get_battle_opponent(battle, current_user)
    progress = calculate_progress(battle["player_one_score"], battle["player_two_score"])
    player_one_track = "blue-track" if battle["id"] % 2 == 0 else "red-track"
    player_two_track = "red-track" if player_one_track == "blue-track" else "blue-track"

    if battle["battle_type"] == "bot":
        your_score = battle["player_one_score"]
        opponent_score = battle["player_two_score"]
        your_lives = battle["player_one_lives"]
        opponent_lives = battle["player_two_lives"]
        your_track_class = player_one_track
        opponent_track_class = player_two_track
    elif side == "player_one":
        your_score = battle["player_one_score"]
        opponent_score = battle["player_two_score"]
        your_lives = None
        opponent_lives = None
        your_track_class = player_one_track
        opponent_track_class = player_two_track
    else:
        your_score = battle["player_two_score"]
        opponent_score = battle["player_one_score"]
        your_lives = None
        opponent_lives = None
        progress = 100 - progress
        your_track_class = player_two_track
        opponent_track_class = player_one_track

    return {
        "side": side,
        "opponent": opponent,
        "progress": progress,
        "your_score": your_score,
        "opponent_score": opponent_score,
        "your_lives": your_lives,
        "opponent_lives": opponent_lives,
        "your_track_class": your_track_class,
        "opponent_track_class": opponent_track_class,
    }


def get_ready_check_state(battle, current_user):
    side = get_player_side(battle, current_user["id"])
    opponent = get_battle_opponent(battle, current_user)

    your_ready = battle["player_one_ready"] if side == "player_one" else battle["player_two_ready"]
    opponent_ready = battle["player_two_ready"] if side == "player_one" else battle["player_one_ready"]

    return {
        "side": side,
        "opponent": opponent,
        "your_ready": bool(your_ready),
        "opponent_ready": bool(opponent_ready),
    }


def get_ready_remaining_seconds(battle):
    ready_started_at = battle.get("ready_started_at")
    if not ready_started_at:
        return 0
    if isinstance(ready_started_at, datetime):
        started_dt = ready_started_at
    else:
        started_dt = datetime.strptime(ready_started_at, "%Y-%m-%d %H:%M:%S")
    deadline = started_dt + timedelta(seconds=15)
    return max(0, int((deadline - datetime.now()).total_seconds()))


def maybe_expire_ready_check(battle):
    if battle["status"] != "ready_check":
        return battle

    if get_ready_remaining_seconds(battle) > 0:
        return battle

    delete_battle(battle["id"])
    return None


def parse_battle_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def get_next_ai_action_at(level_config, task=None, level_code=None):
    delay_seconds = pick_ai_delay(level_config, task, level_code)
    return datetime.now() + timedelta(seconds=delay_seconds)


def get_ai_state(battle):
    next_action_at = parse_battle_timestamp(battle.get("player_two_next_action_at"))
    if not next_action_at:
        return {
            "thinking": False,
            "remaining_seconds": None,
        }

    remaining = max(0.0, (next_action_at - datetime.now()).total_seconds())
    return {
        "thinking": remaining > 0,
        "remaining_seconds": round(remaining, 1),
    }


def get_battle_language(battle):
    if battle["battle_type"] == "pvp":
        owner_row = get_user_by_id(battle["player_one_id"])
        if owner_row and owner_row[3]:
            return normalize_language(owner_row[3])
    return "ru"


def ensure_pvp_task_buffer(battle, minimum_ahead=8):
    if not battle or battle["battle_type"] != "pvp":
        return battle

    tasks = loads_data(battle["tasks_json"], [])
    player_one_answers = loads_data(battle["player_one_answers"], [])
    player_two_answers = loads_data(battle["player_two_answers"], [])
    furthest_index = max(len(player_one_answers), len(player_two_answers))

    if len(tasks) - furthest_index > minimum_ahead:
        return battle

    language = get_battle_language(battle)
    extra_tasks = generate_battle_tasks(minimum_ahead + 6, language)
    tasks.extend(extra_tasks)
    update_battle_tasks(battle["id"], dumps_data(tasks))
    return get_battle_by_id(battle["id"])


def advance_bot_battle_if_needed(app, battle, language):
    if not battle or battle["battle_type"] != "bot" or battle["status"] != "active":
        return battle

    tasks = loads_data(battle["tasks_json"], [])
    player_one_answers = loads_data(battle["player_one_answers"], [])
    player_two_answers = loads_data(battle["player_two_answers"], [])
    player_one_times = loads_data(battle["player_one_times"], [])
    player_two_times = loads_data(battle["player_two_times"], [])

    if len(player_two_answers) >= len(tasks):
        return battle

    bot_level = get_bot_level_config(app.config["BOT_LEVELS"], battle["bot_level"])
    if not bot_level:
        return battle

    next_action_at = parse_battle_timestamp(battle.get("player_two_next_action_at"))
    if next_action_at is None:
        current_task = tasks[len(player_two_answers)] if len(player_two_answers) < len(tasks) else None
        next_action_at = get_next_ai_action_at(bot_level, current_task, battle["bot_level"])
        update_battle_state(
            battle["id"],
            battle["player_one_score"],
            battle["player_two_score"],
            dumps_data(player_one_answers),
            dumps_data(player_two_answers),
            dumps_data(player_one_times),
            dumps_data(player_two_times),
            battle["player_one_lives"],
            battle["player_two_lives"],
            next_action_at,
        )
        return get_battle_by_id(battle["id"])

    now = datetime.now()
    progressed = False

    while next_action_at and now >= next_action_at and len(player_two_answers) < len(tasks) and battle["status"] == "active":
        current_task = tasks[len(player_two_answers)]
        response_seconds = pick_ai_delay(bot_level, current_task, battle["bot_level"])
        bot_result = get_gemini_answer_data(
            current_task,
            battle["bot_level"],
            bot_level,
            app.config.get("GEMINI_API_KEY", ""),
            app.config.get("GEMINI_MODEL", "gemini-2.5-flash"),
            language,
            response_seconds=response_seconds,
        )
        player_two_answers.append(bot_result["answer"])
        player_two_times.append(bot_result["response_seconds"])
        battle["player_two_score"] += bot_result["score"]
        if not bot_result["is_correct"]:
            current_lives = battle["player_two_lives"] if battle["player_two_lives"] is not None else 3
            battle["player_two_lives"] = max(0, current_lives - 1)

        progressed = True
        if len(player_two_answers) >= len(tasks):
            next_action_at = None
        else:
            upcoming_task = tasks[len(player_two_answers)] if len(player_two_answers) < len(tasks) else None
            next_action_at = now + timedelta(seconds=pick_ai_delay(bot_level, upcoming_task, battle["bot_level"]))

    if not progressed:
        return battle

    update_battle_state(
        battle["id"],
        battle["player_one_score"],
        battle["player_two_score"],
        dumps_data(player_one_answers),
        dumps_data(player_two_answers),
        dumps_data(player_one_times),
        dumps_data(player_two_times),
        battle["player_one_lives"],
        battle["player_two_lives"],
        next_action_at,
    )
    return get_battle_by_id(battle["id"])


def finalize_real_battle(battle, player_one, player_two):
    score_diff = abs(battle["player_one_score"] - battle["player_two_score"])

    if battle["player_one_score"] == battle["player_two_score"]:
        add_battle_result_to_user(player_one["id"], "draw")
        add_battle_result_to_user(player_two["id"], "draw")
        finish_battle(battle["id"], None, DRAW_MARKER, player_one_elo_delta=0, player_two_elo_delta=0)
        return {
            "winner_name": DRAW_MARKER,
            "elo_gain": 0,
        }

    if battle["player_one_score"] > battle["player_two_score"]:
        winner = player_one
        loser = player_two
    elif battle["player_two_score"] > battle["player_one_score"]:
        winner = player_two
        loser = player_one

    elo_gain = calculate_elo_change(score_diff)
    winner_new_elo = winner["elo"] + elo_gain
    loser_new_elo = max(800, loser["elo"] - elo_gain)

    update_user_elo(winner["id"], winner_new_elo)
    update_user_elo(loser["id"], loser_new_elo)
    add_battle_result_to_user(winner["id"], "win")
    add_battle_result_to_user(loser["id"], "loss")
    add_user_points(winner["id"], max(50, battle["player_one_score"] if winner["id"] == player_one["id"] else battle["player_two_score"]))
    finish_battle(
        battle["id"],
        winner["id"],
        winner["name"],
        player_one_elo_delta=elo_gain if winner["id"] == player_one["id"] else -elo_gain,
        player_two_elo_delta=elo_gain if winner["id"] == player_two["id"] else -elo_gain,
    )

    return {
        "winner_name": winner["name"],
        "elo_gain": elo_gain,
    }


def surrender_battle_for_user(battle, current_user):
    if battle["battle_type"] == "bot":
        finish_battle(battle["id"], None, f"AI {battle['bot_level'].capitalize()}")
        return

    side = get_player_side(battle, current_user["id"])
    if side is None:
        return

    winner_id = battle["player_two_id"] if side == "player_one" else battle["player_one_id"]
    winner_row = get_user_by_id(winner_id)
    loser_row = get_user_by_id(current_user["id"])
    if not winner_row or not loser_row:
        return

    winner = format_user_card(winner_row)
    loser = format_user_card(loser_row)
    winner_elo_gain = 10
    loser_elo_penalty = 30

    update_user_elo(winner["id"], winner["elo"] + winner_elo_gain)
    update_user_elo(loser["id"], max(800, loser["elo"] - loser_elo_penalty))
    add_battle_result_to_user(winner["id"], "win")
    add_battle_result_to_user(loser["id"], "loss")
    add_user_points(winner["id"], 50)
    finish_battle(
        battle["id"],
        winner["id"],
        winner["name"],
        player_one_elo_delta=winner_elo_gain if winner["id"] == battle["player_one_id"] else -loser_elo_penalty,
        player_two_elo_delta=winner_elo_gain if winner["id"] == battle["player_two_id"] else -loser_elo_penalty,
    )


def maybe_finish_battle(app, battle):
    if battle["status"] != "active":
        return battle

    tasks = loads_data(battle["tasks_json"], [])
    player_one_answers = loads_data(battle["player_one_answers"], [])
    player_two_answers = loads_data(battle["player_two_answers"], [])
    remaining = get_battle_remaining_seconds(battle["started_at"], battle["time_limit"])

    should_finish = False

    if battle["battle_type"] == "bot":
        player_one_lives = battle["player_one_lives"] if battle["player_one_lives"] is not None else 3
        player_two_lives = battle["player_two_lives"] if battle["player_two_lives"] is not None else 3
        if player_one_lives <= 0 or player_two_lives <= 0:
            should_finish = True
        if len(player_one_answers) >= len(tasks) or len(player_two_answers) >= len(tasks):
            should_finish = True
    else:
        if is_pushout(battle["player_one_score"], battle["player_two_score"]):
            should_finish = True

    if remaining <= 0:
        should_finish = True

    if not should_finish:
        return battle

    if battle["battle_type"] == "bot":
        winner_name = "AI"
        winner_id = None

        if battle["player_one_lives"] > battle["player_two_lives"]:
            winner_name = get_user_by_id(battle["player_one_id"])[1]
            winner_id = battle["player_one_id"]
        elif battle["player_two_lives"] > battle["player_one_lives"]:
            winner_name = f"AI {battle['bot_level'].capitalize()}"
        elif battle["player_one_score"] > battle["player_two_score"]:
            winner_name = get_user_by_id(battle["player_one_id"])[1]
            winner_id = battle["player_one_id"]
        elif battle["player_two_score"] > battle["player_one_score"]:
            winner_name = f"AI {battle['bot_level'].capitalize()}"
        else:
            winner_name = DRAW_MARKER
            winner_id = None

        finish_battle(battle["id"], winner_id, winner_name)
    else:
        player_one = format_user_card(get_user_by_id(battle["player_one_id"]))
        player_two = format_user_card(get_user_by_id(battle["player_two_id"]))
        finalize_real_battle(battle, player_one, player_two)

    return get_battle_by_id(battle["id"])


def build_profile_battle_stats(user_id, current_user):
    finished_battles = get_finished_pvp_battles_for_user(user_id)
    total_matches = len(finished_battles)
    wins = 0
    losses = 0
    draws = 0
    win_percent = round((wins / total_matches) * 100, 1) if total_matches else 0

    answered_total = 0
    answered_correct = 0

    for battle in finished_battles:
        if is_draw_value(battle["winner_name"]):
            draws += 1
        elif battle["winner_id"] == user_id:
            wins += 1
        else:
            losses += 1

        tasks = loads_data(battle["tasks_json"], [])
        if battle["player_one_id"] == user_id:
            answers = loads_data(battle["player_one_answers"], [])
        else:
            answers = loads_data(battle["player_two_answers"], [])

        for index, answer in enumerate(answers):
            if index >= len(tasks):
                break
            answered_total += 1
            if answer == tasks[index]["a"]:
                answered_correct += 1

    win_percent = round((wins / total_matches) * 100, 1) if total_matches else 0
    accuracy_percent = round((answered_correct / answered_total) * 100, 1) if answered_total else 0

    return {
        "total_matches": total_matches,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_percent": win_percent,
        "accuracy_percent": accuracy_percent,
    }


def build_overall_stats(user_id):
    training_rows = get_all_results(user_id)
    pvp_battles = get_finished_pvp_battles_for_user(user_id)

    training_attempts = len(training_rows)
    battle_matches = len(pvp_battles)
    total_activities = training_attempts + battle_matches

    correct_answers = 0
    total_answers = 0

    for row in training_rows:
        correct_answers += row[4]
        total_answers += row[5]

    battle_wins = 0
    battle_losses = 0
    battle_draws = 0
    battle_correct = 0
    battle_total_answers = 0

    for battle in pvp_battles:
        if is_draw_value(battle["winner_name"]):
            battle_draws += 1
        elif battle["winner_id"] == user_id:
            battle_wins += 1
        else:
            battle_losses += 1

        tasks = loads_data(battle["tasks_json"], [])
        if battle["player_one_id"] == user_id:
            answers = loads_data(battle["player_one_answers"], [])
        else:
            answers = loads_data(battle["player_two_answers"], [])

        for index, answer in enumerate(answers):
            if index >= len(tasks):
                break
            battle_total_answers += 1
            if answer == tasks[index]["a"]:
                battle_correct += 1

    correct_answers += battle_correct
    total_answers += battle_total_answers

    overall_accuracy = round((correct_answers / total_answers) * 100, 2) if total_answers else 0

    return {
        "training_attempts": training_attempts,
        "battle_matches": battle_matches,
        "total_activities": total_activities,
        "overall_accuracy": overall_accuracy,
        "battle_wins": battle_wins,
        "battle_losses": battle_losses,
        "battle_draws": battle_draws,
    }


def build_profile_leaderboards(current_user_id):
    leaderboard_users = [format_user_card(row) for row in get_all_users_for_leaderboard()]
    leaderboard_entries = []

    for user in leaderboard_users:
        stats = build_profile_battle_stats(user["id"], user)
        leaderboard_entries.append(
            {
                "user": user,
                "stats": stats,
                "is_current_user": user["id"] == current_user_id,
            }
        )

    top_elo = sorted(
        leaderboard_entries,
        key=lambda entry: (-entry["user"]["elo"], entry["user"]["name"].lower()),
    )[:5]

    top_wins = sorted(
        [entry for entry in leaderboard_entries if entry["stats"]["total_matches"] > 0],
        key=lambda entry: (-entry["stats"]["wins"], -entry["user"]["elo"], entry["user"]["name"].lower()),
    )[:5]

    top_accuracy = sorted(
        [entry for entry in leaderboard_entries if entry["stats"]["total_matches"] > 0],
        key=lambda entry: (
            -entry["stats"]["accuracy_percent"],
            -entry["stats"]["total_matches"],
            -entry["user"]["elo"],
            entry["user"]["name"].lower(),
        ),
    )[:5]

    return {
        "elo": top_elo,
        "wins": top_wins,
        "accuracy": top_accuracy,
    }


def parse_battle_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def format_match_duration(started_at, finished_at):
    start_dt = parse_battle_datetime(started_at)
    finish_dt = parse_battle_datetime(finished_at)
    if not start_dt or not finish_dt:
        return "—"
    total_seconds = max(0, int((finish_dt - start_dt).total_seconds()))
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def build_profile_dashboard(user_id):
    battles = list(reversed(get_finished_pvp_battles_for_user(user_id)))
    current_user = get_current_user()
    current_elo = current_user["elo"] if current_user else 1000

    elo_points = []
    for battle in reversed(battles):
        if battle["player_one_id"] == user_id:
            current_elo -= battle.get("player_one_elo_delta", 0) or 0
        else:
            current_elo -= battle.get("player_two_elo_delta", 0) or 0

    elo_points.append({"label": "Start", "elo": current_elo})

    longest_winstreak = 0
    current_streak = 0
    history_rows = []

    for index, battle in enumerate(battles, start=1):
        if battle["player_one_id"] == user_id:
            opponent_id = battle["player_two_id"]
            your_score = battle["player_one_score"]
            opponent_score = battle["player_two_score"]
            elo_delta = battle.get("player_one_elo_delta", 0) or 0
        else:
            opponent_id = battle["player_one_id"]
            your_score = battle["player_two_score"]
            opponent_score = battle["player_one_score"]
            elo_delta = battle.get("player_two_elo_delta", 0) or 0

        opponent_row = get_user_by_id(opponent_id) if opponent_id else None
        opponent_name = opponent_row[1] if opponent_row else t("common.unknown")

        if is_draw_value(battle["winner_name"]):
            result_key = "draw"
            current_streak = 0
        elif battle["winner_id"] == user_id:
            result_key = "win"
            current_streak += 1
            longest_winstreak = max(longest_winstreak, current_streak)
        else:
            result_key = "loss"
            current_streak = 0

        current_elo += elo_delta
        elo_points.append(
            {
                "label": f"M{index}",
                "elo": current_elo,
            }
        )

        history_rows.append(
            {
                "id": battle["id"],
                "opponent_name": opponent_name,
                "result_key": result_key,
                "result_label": t(f"result.{result_key}"),
                "your_score": your_score,
                "opponent_score": opponent_score,
                "elo_delta": elo_delta,
                "elo_delta_label": f"{elo_delta:+d}",
                "created_at": format_datetime(battle["finished_at"] or battle["started_at"]),
                "duration": format_match_duration(battle["started_at"], battle["finished_at"]),
            }
        )

    battle_stats = build_profile_battle_stats(user_id, current_user)
    return {
        "elo_points": elo_points,
        "winrate": battle_stats["win_percent"],
        "longest_winstreak": longest_winstreak,
        "matches": battle_stats["total_matches"],
        "history_rows": list(reversed(history_rows)),
    }


def register_routes(app):
    @app.context_processor
    def inject_current_user():
        current_user = get_current_user()
        current_lang = get_current_language(current_user)
        return {
            "current_user": current_user,
            "current_lang": current_lang,
            "player_themes": app.config["PLAYER_THEMES"],
            "language_options": LANGUAGE_OPTIONS,
            "tr": lambda key, **kwargs: translate(key, current_lang, **kwargs),
            "theme_label": lambda code: translate_theme(code, current_lang),
            "section_label": lambda section: translate_section(section, current_lang),
            "level_label": lambda level: translate_level(level, current_lang),
            "mode_label": lambda mode: translate_mode(mode, current_lang),
        }

    @app.after_request
    def add_no_store_headers(response):
        if request.path.startswith("/battle") or request.path in {"/task", "/finish"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.route("/")
    def home():
        return render_template("index.html", auth_error=None, auth_success=None)

    @app.route("/set_language", methods=["POST"])
    def set_language():
        language = normalize_language(request.form.get("language", "ru"))
        session["lang"] = language

        current_user = get_current_user()
        if current_user:
            update_user_language(current_user["id"], language)

        next_url = request.form.get("next") or request.referrer or url_for("home")
        return redirect(next_url)

    @app.route("/register", methods=["POST"])
    def register():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        card_theme = request.form.get("card_theme", "blue")
        language = get_current_language()

        if card_theme not in app.config["PLAYER_THEMES"]:
            card_theme = "blue"

        if not name or not email or not password:
            return render_template("index.html", auth_error=translate("error.fill_register", language), auth_success=None)

        if get_user_by_email(email):
            return render_template("index.html", auth_error=translate("error.user_exists", language), auth_success=None)

        password_hash = generate_password_hash(password)

        try:
            user = create_user_account_with_language(name, email, password_hash, language, card_theme)
        except Exception:
            return render_template("index.html", auth_error=translate("error.create_account", language), auth_success=None)

        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["lang"] = normalize_language(user[3])
        session["card_theme"] = user[4]
        clear_game_session(session)

        return redirect(url_for("profile"))

    @app.route("/login", methods=["POST"])
    def login():
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        language = get_current_language()

        if not email or not password:
            return render_template("index.html", auth_error=translate("error.fill_login", language), auth_success=None)

        user = get_user_by_email(email)
        if not user:
            return render_template("index.html", auth_error=translate("error.user_not_found", language), auth_success=None)
        if not user[3] or not check_password_hash(user[3], password):
            return render_template("index.html", auth_error=translate("error.wrong_password", normalize_language(user[4])), auth_success=None)

        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["lang"] = normalize_language(user[4])
        session["card_theme"] = user[5]
        clear_game_session(session)

        return redirect(url_for("profile"))

    @app.route("/logout")
    def logout():
        language = session.get("lang")
        session.clear()
        if language:
            session["lang"] = language
        return redirect(url_for("home"))

    @app.route("/learning")
    def learning():
        return render_template("learning.html")

    @app.route("/battle")
    def battle():
        current_user = require_current_user()
        if not current_user:
            return render_template(
                "battle.html",
                active_battles=[],
                recent_battles=[],
                bot_levels=app.config["BOT_LEVELS"],
                open_pvp_battle=None,
            )

        open_pvp_battle = get_user_open_pvp_battle(current_user["id"])
        if open_pvp_battle:
            open_pvp_battle = maybe_expire_ready_check(open_pvp_battle)

        active_battles = []
        for battle_row in get_active_battles_for_user(current_user["id"]):
            active_battles.append(
                {
                    "id": battle_row["id"],
                    "type": battle_row["battle_type"],
                    "status": battle_row["status"],
                    "opponent": get_battle_opponent(battle_row, current_user),
                    "score_line": f"{battle_row['player_one_score']} : {battle_row['player_two_score']}",
                }
            )

        recent_battles = []
        for battle_row in get_recent_battles_for_user(current_user["id"], 5):
            if is_draw_value(battle_row["winner_name"]):
                winner_name = t("result.draw")
            elif (
                battle_row["battle_type"] == "bot"
                and battle_row["winner_name"]
                and battle_row["winner_name"].startswith("AI ")
            ):
                winner_level = battle_row["winner_name"].split(" ", 1)[1].lower()
                winner_name = translate_bot_level(winner_level, language)
            else:
                winner_name = battle_row["winner_name"]

            recent_battles.append(
                {
                    "id": battle_row["id"],
                    "type": battle_row["battle_type"],
                    "winner_name": winner_name,
                    "score_line": f"{battle_row['player_one_score']} : {battle_row['player_two_score']}",
                }
            )

        return render_template(
            "battle.html",
            active_battles=active_battles,
            recent_battles=recent_battles,
            bot_levels=app.config["BOT_LEVELS"],
            open_pvp_battle=open_pvp_battle,
        )

    @app.route("/sounds/<path:filename>")
    def sounds(filename):
        sounds_dir = os.path.join(app.root_path, "..", "sounds")
        return send_from_directory(sounds_dir, filename)

    @app.route("/image/icon/<path:filename>")
    def icon_image(filename):
        icons_dir = os.path.join(app.root_path, "..", "image", "icon")
        return send_from_directory(icons_dir, filename)

    @app.route("/battle/create-bot", methods=["POST"])
    def create_bot_battle():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        bot_level_code = request.form.get("bot_level", "easy")
        bot_level = get_bot_level_config(app.config["BOT_LEVELS"], bot_level_code)
        if not bot_level:
            return redirect(url_for("battle"))

        tasks = generate_battle_tasks(app.config["BOT_BATTLE_TASKS_COUNT"], get_current_language(current_user))
        first_ai_action_at = get_next_ai_action_at(
            bot_level,
            tasks[0] if tasks else None,
            bot_level_code,
        )
        battle_id = create_battle(
            battle_type="bot",
            ranked=False,
            player_one_id=current_user["id"],
            player_two_id=None,
            bot_level=bot_level_code,
            player_one_lives=3,
            player_two_lives=3,
            player_two_next_action_at=first_ai_action_at,
            tasks_json=dumps_data(tasks),
            time_limit=app.config["BATTLE_TIME_LIMIT"],
        )
        return redirect(url_for("battle_match", battle_id=battle_id))

    @app.route("/battle/search-pvp", methods=["POST"])
    def search_pvp_battle():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        existing_battle = get_user_open_pvp_battle(current_user["id"])
        if existing_battle:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"status": existing_battle["status"], "battle_id": existing_battle["id"]})
            return redirect(url_for("battle_match", battle_id=existing_battle["id"]))

        tasks = generate_battle_tasks(app.config["PVP_BATTLE_TASKS_COUNT"], get_current_language(current_user))
        battle_id = join_or_create_pvp_battle(
            current_user["id"],
            dumps_data(tasks),
            app.config["BATTLE_TIME_LIMIT"],
        )
        created_battle = get_battle_by_id(battle_id)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": created_battle["status"], "battle_id": battle_id})
        return redirect(url_for("battle_match", battle_id=battle_id))

    @app.route("/battle/pvp-state")
    def pvp_battle_state():
        current_user = require_current_user()
        if not current_user:
            return jsonify({"status": "unauthorized", "redirect_url": url_for("home")}), 401

        battle = get_user_open_pvp_battle(current_user["id"])
        if not battle:
            return jsonify({"status": "idle"})

        battle = maybe_expire_ready_check(battle)
        if not battle:
            return jsonify({"status": "expired"})

        if battle["status"] == "waiting":
            return jsonify({"status": "waiting", "battle_id": battle["id"]})

        if battle["status"] == "ready_check":
            ready_state = get_ready_check_state(battle, current_user)
            return jsonify(
                {
                    "status": "ready_check",
                    "battle_id": battle["id"],
                    "opponent_name": ready_state["opponent"]["name"] if ready_state["opponent"] else t("common.unknown"),
                    "your_ready": ready_state["your_ready"],
                    "opponent_ready": ready_state["opponent_ready"],
                    "ready_remaining_seconds": get_ready_remaining_seconds(battle),
                }
            )

        return jsonify({"status": "active", "battle_id": battle["id"], "redirect_url": url_for("battle_match", battle_id=battle["id"])})

    @app.route("/battle/cancel-search", methods=["POST"])
    def cancel_search_pvp_inline():
        current_user = require_current_user()
        if not current_user:
            return jsonify({"redirect_url": url_for("home")}), 401

        open_battle = get_user_open_pvp_battle(current_user["id"])
        if open_battle:
            cancel_waiting_pvp_battle(open_battle["id"], current_user["id"])

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "cancelled"})
        return redirect(url_for("battle"))

    @app.route("/battle/match/<int:battle_id>/accept", methods=["POST"])
    def accept_pvp_battle(battle_id):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        battle = get_battle_by_id(battle_id)
        if not battle or battle["battle_type"] != "pvp":
            return redirect(url_for("battle"))

        side = get_player_side(battle, current_user["id"])
        if side is None:
            return redirect(url_for("battle"))

        if battle["status"] == "waiting":
            return redirect(url_for("battle_match", battle_id=battle_id))

        if battle["status"] == "ready_check":
            set_battle_ready_state(battle_id, side, True)
            activated_battle = try_activate_ready_battle(battle_id)
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                if activated_battle:
                    return jsonify({"status": "active", "redirect_url": url_for("battle_match", battle_id=battle_id)})
                refreshed_battle = get_battle_by_id(battle_id)
                refreshed_state = get_ready_check_state(refreshed_battle, current_user)
                return jsonify(
                    {
                        "status": "ready_check",
                        "battle_id": battle_id,
                        "your_ready": refreshed_state["your_ready"],
                        "opponent_ready": refreshed_state["opponent_ready"],
                        "ready_remaining_seconds": get_ready_remaining_seconds(refreshed_battle),
                    }
                )
            if activated_battle:
                return redirect(url_for("battle_match", battle_id=battle_id))

        return redirect(url_for("battle_match", battle_id=battle_id))

    @app.route("/battle/cancel-search/<int:battle_id>", methods=["POST"])
    def cancel_search_pvp(battle_id):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        cancel_waiting_pvp_battle(battle_id, current_user["id"])
        return redirect(url_for("battle"))

    @app.route("/battle/match/<int:battle_id>")
    def battle_match(battle_id):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        battle = get_battle_by_id(battle_id)
        if not battle:
            return redirect(url_for("battle"))
        battle = maybe_expire_ready_check(battle)
        if not battle:
            return redirect(url_for("battle"))

        side = get_player_side(battle, current_user["id"])
        if battle["battle_type"] == "pvp" and battle["status"] == "waiting" and battle["player_one_id"] == current_user["id"]:
            return render_template("battle_waiting.html", battle=battle, ready_state=None)
        if battle["battle_type"] == "pvp" and battle["status"] == "ready_check":
            ready_state = get_ready_check_state(battle, current_user)
            return render_template(
                "battle_waiting.html",
                battle=battle,
                ready_state=ready_state,
                ready_remaining_seconds=get_ready_remaining_seconds(battle),
            )
        if battle["battle_type"] == "pvp" and side is None:
            return redirect(url_for("battle"))
        if battle["battle_type"] == "bot" and battle["player_one_id"] != current_user["id"]:
            return redirect(url_for("battle"))

        if battle["battle_type"] == "bot":
            battle = advance_bot_battle_if_needed(app, battle, get_current_language(current_user))
        else:
            battle = ensure_pvp_task_buffer(battle)
        battle = maybe_finish_battle(app, battle)
        tasks = loads_data(battle["tasks_json"], [])
        player_one_answers = loads_data(battle["player_one_answers"], [])
        player_two_answers = loads_data(battle["player_two_answers"], [])
        player_one_times = loads_data(battle["player_one_times"], [])
        player_two_times = loads_data(battle["player_two_times"], [])

        if battle["status"] != "active":
            opponent = get_battle_opponent(battle, current_user)
            battle_view = get_battle_view_state(battle, current_user)
            refreshed_current_user = get_current_user()
            refreshed_opponent = opponent
            if battle["battle_type"] == "pvp" and opponent and opponent["id"]:
                refreshed_opponent = format_user_card(get_user_by_id(opponent["id"]))
            is_draw = is_draw_value(battle["winner_name"])
            result_outcome = "draw"
            if not is_draw:
                result_outcome = "win" if battle["winner_id"] == current_user["id"] else "loss"
            return render_template(
                "battle_result.html",
                battle=battle,
                opponent=refreshed_opponent,
                progress=battle_view["progress"],
                your_track_class=battle_view["your_track_class"],
                opponent_track_class=battle_view["opponent_track_class"],
                your_score=battle_view["your_score"],
                opponent_score=battle_view["opponent_score"],
                current_user=refreshed_current_user,
                is_draw=is_draw,
                result_outcome=result_outcome,
            )

        if battle["battle_type"] == "bot":
            current_answers = player_one_answers
            current_times = player_one_times
            current_task, current_index = get_current_battle_question(tasks, current_answers)
        elif side == "player_one":
            current_answers = player_one_answers
            current_times = player_one_times
            current_task, current_index = get_current_battle_question(tasks, current_answers)
        else:
            current_answers = player_two_answers
            current_times = player_two_times
            current_task, current_index = get_current_battle_question(tasks, current_answers)

        remaining_seconds = get_battle_remaining_seconds(battle["started_at"], battle["time_limit"])
        battle_view = get_battle_view_state(battle, current_user)

        return render_template(
            "battle_match.html",
            battle=battle,
            opponent=battle_view["opponent"],
            current_task=current_task,
            current_index=current_index + 1,
            total_tasks=len(tasks),
            total_tasks_label="∞" if battle["battle_type"] == "pvp" else str(len(tasks)),
            remaining_seconds=remaining_seconds,
            battle_deadline_ts=get_battle_deadline_timestamp(battle["started_at"], battle["time_limit"]),
            progress=battle_view["progress"],
            your_track_class=battle_view["your_track_class"],
            opponent_track_class=battle_view["opponent_track_class"],
            your_score=battle_view["your_score"],
            opponent_score=battle_view["opponent_score"],
            your_lives=battle_view["your_lives"],
            opponent_lives=battle_view["opponent_lives"],
            current_user=current_user,
            background_audio_url=url_for(
                "sounds",
                filename="background_bot.mp3" if battle["battle_type"] == "bot" else "background_music.mp3",
            ),
            sound_on_icon_url=url_for("icon_image", filename="sound_on.png"),
            sound_off_icon_url=url_for("icon_image", filename="sound_off.png"),
            last_answer_submitted=request.args.get("answered") == "1",
            last_answer_correct=request.args.get("correct") == "1",
            last_answer_score=int(request.args.get("last_score", "0") or "0"),
            your_answer_count=len(current_answers),
            opponent_answer_count=(
                len(player_two_answers)
                if battle["battle_type"] == "bot" or side == "player_one"
                else len(player_one_answers)
            ),
            ai_state=get_ai_state(battle) if battle["battle_type"] == "bot" else None,
        )

    @app.route("/battle/match/<int:battle_id>/status")
    def battle_match_status(battle_id):
        current_user = require_current_user()
        if not current_user:
            return jsonify({"redirect_url": url_for("home")}), 401

        battle = get_battle_by_id(battle_id)
        if not battle:
            return jsonify({"redirect_url": url_for("battle")}), 404
        battle = maybe_expire_ready_check(battle)
        if not battle:
            return jsonify({"status": "expired", "redirect_url": url_for("battle")})

        side = get_player_side(battle, current_user["id"])
        if battle["battle_type"] == "pvp" and side is None:
            return jsonify({"redirect_url": url_for("battle")}), 403
        if battle["battle_type"] == "bot" and battle["player_one_id"] != current_user["id"]:
            return jsonify({"redirect_url": url_for("battle")}), 403

        if battle["battle_type"] == "bot":
            battle = advance_bot_battle_if_needed(app, battle, get_current_language(current_user))
        else:
            battle = ensure_pvp_task_buffer(battle)

        if battle["battle_type"] == "pvp" and battle["status"] == "waiting" and battle["player_one_id"] == current_user["id"]:
            return jsonify({"status": "waiting"})
        if battle["battle_type"] == "pvp" and battle["status"] == "ready_check":
            ready_state = get_ready_check_state(battle, current_user)
            activated_battle = try_activate_ready_battle(battle_id)
            if activated_battle:
                return jsonify(
                    {
                        "status": "active",
                        "redirect_url": url_for("battle_match", battle_id=battle_id),
                    }
                )
            return jsonify(
                {
                    "status": "ready_check",
                    "your_ready": ready_state["your_ready"],
                    "opponent_ready": ready_state["opponent_ready"],
                    "opponent_name": ready_state["opponent"]["name"] if ready_state["opponent"] else t("common.unknown"),
                    "ready_remaining_seconds": get_ready_remaining_seconds(battle),
                }
            )

        battle = maybe_finish_battle(app, battle)
        if battle["status"] != "active":
            return jsonify(
                {
                    "status": battle["status"],
                    "redirect_url": url_for("battle_match", battle_id=battle_id),
                }
            )

        battle_view = get_battle_view_state(battle, current_user)
        tasks = loads_data(battle["tasks_json"], [])
        if battle["battle_type"] == "bot":
            current_answers = loads_data(battle["player_one_answers"], [])
        elif battle_view["side"] == "player_one":
            current_answers = loads_data(battle["player_one_answers"], [])
        else:
            current_answers = loads_data(battle["player_two_answers"], [])

        _, current_index = get_current_battle_question(tasks, current_answers)

        return jsonify(
            {
                "status": "active",
                "progress": battle_view["progress"],
                "your_score": battle_view["your_score"],
                "opponent_score": battle_view["opponent_score"],
                "your_lives": battle_view["your_lives"],
                "opponent_lives": battle_view["opponent_lives"],
                "opponent_name": battle_view["opponent"]["name"] if battle_view["opponent"] else t("common.unknown"),
                "remaining_seconds": get_battle_remaining_seconds(battle["started_at"], battle["time_limit"]),
                "battle_deadline_ts": get_battle_deadline_timestamp(battle["started_at"], battle["time_limit"]),
                "current_index": current_index + 1,
                "total_tasks_label": "∞" if battle["battle_type"] == "pvp" else str(len(tasks)),
                "your_answer_count": len(current_answers),
                "opponent_answer_count": (
                    len(loads_data(battle["player_two_answers"], []))
                    if battle["battle_type"] == "bot" or battle_view["side"] == "player_one"
                    else len(loads_data(battle["player_one_answers"], []))
                ),
                "ai_thinking": get_ai_state(battle)["thinking"] if battle["battle_type"] == "bot" else False,
                "ai_next_action_seconds": get_ai_state(battle)["remaining_seconds"] if battle["battle_type"] == "bot" else None,
            }
        )

    @app.route("/battle/match/<int:battle_id>/answer", methods=["POST"])
    def battle_answer(battle_id):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        battle = get_battle_by_id(battle_id)
        if not battle or battle["status"] != "active":
            return redirect(url_for("battle_match", battle_id=battle_id))

        if battle["battle_type"] == "bot":
            battle = advance_bot_battle_if_needed(app, battle, get_current_language(current_user))
            battle = maybe_finish_battle(app, battle)
            if battle["status"] != "active":
                return redirect(url_for("battle_match", battle_id=battle_id))
        else:
            battle = ensure_pvp_task_buffer(battle)

        tasks = loads_data(battle["tasks_json"], [])
        player_one_answers = loads_data(battle["player_one_answers"], [])
        player_two_answers = loads_data(battle["player_two_answers"], [])
        player_one_times = loads_data(battle["player_one_times"], [])
        player_two_times = loads_data(battle["player_two_times"], [])

        if battle["battle_type"] == "bot":
            side = "player_one"
            current_answers = player_one_answers
            current_task, current_index = get_current_battle_question(tasks, current_answers)
        else:
            side = get_player_side(battle, current_user["id"])
            if side is None:
                return redirect(url_for("battle"))
            current_answers = player_one_answers if side == "player_one" else player_two_answers
            current_task, current_index = get_current_battle_question(tasks, current_answers)

        if current_task is None:
            return redirect(url_for("battle_match", battle_id=battle_id))

        response_seconds = max(0.1, float(request.form.get("response_seconds", str(app.config["BATTLE_QUESTION_TIME"])) or str(app.config["BATTLE_QUESTION_TIME"])))
        user_answer_str = request.form.get("user_answer", "").strip()
        user_answer = None
        if user_answer_str != "" and user_answer_str.lstrip("-").isdigit():
            user_answer = int(user_answer_str)

        is_correct = user_answer == current_task["a"]
        answer_score = calculate_answer_score(
            is_correct,
            response_seconds,
            app.config["BATTLE_QUESTION_TIME"],
            app.config["BATTLE_POINTS_POSSIBLE"],
        )

        if side == "player_one":
            player_one_answers.append(user_answer)
            player_one_times.append(response_seconds)
            player_one_score = battle["player_one_score"] + answer_score
            player_two_score = battle["player_two_score"]
            player_one_lives = battle["player_one_lives"]
            player_two_lives = battle["player_two_lives"]
        else:
            player_two_answers.append(user_answer)
            player_two_times.append(response_seconds)
            player_two_score = battle["player_two_score"] + answer_score
            player_one_score = battle["player_one_score"]
            player_one_lives = battle["player_one_lives"]
            player_two_lives = battle["player_two_lives"]

        if battle["battle_type"] == "bot":
            if not is_correct:
                player_one_lives = max(0, player_one_lives - 1)

        update_battle_state(
            battle_id,
            player_one_score,
            player_two_score,
            dumps_data(player_one_answers),
            dumps_data(player_two_answers),
            dumps_data(player_one_times),
            dumps_data(player_two_times),
            player_one_lives,
            player_two_lives,
        )

        return redirect(
            url_for(
                "battle_match",
                battle_id=battle_id,
                answered=1,
                correct=1 if is_correct else 0,
                last_score=answer_score,
            )
        )

    @app.route("/battle/match/<int:battle_id>/surrender", methods=["POST"])
    def battle_surrender(battle_id):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        battle = get_battle_by_id(battle_id)
        if not battle:
            return redirect(url_for("battle"))

        if battle["status"] != "active":
            return redirect(url_for("battle_match", battle_id=battle_id))

        if battle["battle_type"] == "bot":
            if battle["player_one_id"] != current_user["id"]:
                return redirect(url_for("battle"))
        else:
            side = get_player_side(battle, current_user["id"])
            if side is None:
                return redirect(url_for("battle"))

        surrender_battle_for_user(battle, current_user)
        return redirect(url_for("battle_match", battle_id=battle_id))

    @app.route("/set_profile", methods=["POST"])
    def set_profile():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        player_name = request.form.get("player_name", "").strip()
        card_theme = request.form.get("card_theme", "blue")

        if card_theme not in app.config["PLAYER_THEMES"]:
            card_theme = "blue"

        if not player_name:
            battle_stats = build_profile_battle_stats(current_user["id"], current_user)
            return render_template(
                "profile.html",
                player=current_user,
                battle_stats=battle_stats,
                profile_error=t("profile.name_required"),
            )

        try:
            update_user_profile(current_user["id"], player_name, card_theme)
        except Exception:
            battle_stats = build_profile_battle_stats(current_user["id"], current_user)
            return render_template(
                "profile.html",
                player=current_user,
                battle_stats=battle_stats,
                profile_error=t("profile.update_failed"),
            )

        session["user_name"] = player_name
        session["card_theme"] = card_theme
        return redirect(url_for("profile"))

    @app.route("/start/<level>")
    def start_level(level):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        mode = request.args.get("mode", "addsub")
        tasks = generate_math_tasks(level, mode, app.config["TASKS_COUNT"])

        if tasks is None:
            return redirect(url_for("home"))

        session["level"] = level
        session["mode"] = mode
        session["tasks"] = tasks
        session["current"] = 0
        session["user_answers"] = []
        session["result_saved"] = False
        session["started_at"] = None
        session["time_limit"] = None
        session["time_expired"] = False
        session["training_mode"] = True

        return redirect(url_for("task"))

    @app.route("/start/logic/<level>")
    def start_logic(level):
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        tasks = generate_logic_tasks(level, app.config["TASKS_COUNT"], get_current_language(current_user))
        if tasks is None:
            return redirect(url_for("logic_page"))

        session["level"] = level
        session["mode"] = "logic"
        session["tasks"] = tasks
        session["current"] = 0
        session["user_answers"] = []
        session["result_saved"] = False
        session["started_at"] = None
        session["time_limit"] = None
        session["time_expired"] = False
        session["training_mode"] = True

        return redirect(url_for("task"))

    @app.route("/task")
    def task():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        tasks = session.get("tasks")
        current = session.get("current")

        if tasks is None or current is None:
            return redirect(url_for("profile"))

        training_mode = session.get("training_mode", False)
        remaining_seconds = None if training_mode else get_remaining_seconds(session, app.config["TIME_LIMITS"])
        if remaining_seconds == 0:
            session["time_expired"] = True
            return redirect(url_for("finish"))

        if current >= len(tasks):
            return redirect(url_for("finish"))

        question = tasks[current]["q"]
        number = current + 1
        total = len(tasks)
        progress_percent = round((current / total) * 100) if total else 0

        return render_template(
            "task.html",
            question=question,
            number=number,
            total=total,
            progress_percent=progress_percent,
            remaining_seconds=remaining_seconds,
            time_limit=session.get("time_limit"),
            training_mode=training_mode,
            is_logic_task=session.get("mode") == "logic",
        )

    @app.route("/answer", methods=["POST"])
    def answer():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        tasks = session.get("tasks")
        current = session.get("current")
        user_answers = session.get("user_answers")

        if tasks is None or current is None or user_answers is None:
            return redirect(url_for("profile"))

        training_mode = session.get("training_mode", False)
        if not training_mode:
            remaining_seconds = get_remaining_seconds(session, app.config["TIME_LIMITS"])
            if remaining_seconds == 0:
                session["time_expired"] = True
                return redirect(url_for("finish"))

        user_answer_str = request.form.get("user_answer", "").strip()
        user_answer = None
        if user_answer_str != "" and user_answer_str.lstrip("-").isdigit():
            user_answer = int(user_answer_str)

        user_answers.append(user_answer)
        session["user_answers"] = user_answers
        session["current"] = current + 1

        return redirect(url_for("task"))

    @app.route("/history")
    def history():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        training_results = [format_result_row(row) for row in get_all_results(current_user["id"])]
        finished_battles = []
        for battle in get_finished_pvp_battles_for_user(current_user["id"]):
            if battle["player_one_id"] == current_user["id"]:
                opponent_id = battle["player_two_id"]
                your_score = battle["player_one_score"]
                opponent_score = battle["player_two_score"]
            else:
                opponent_id = battle["player_one_id"]
                your_score = battle["player_two_score"]
                opponent_score = battle["player_one_score"]

            opponent_row = get_user_by_id(opponent_id) if opponent_id else None
            opponent_name = opponent_row[1] if opponent_row else t("common.unknown")

            if is_draw_value(battle["winner_name"]):
                result_label = t("result.draw")
            elif battle["winner_id"] == current_user["id"]:
                result_label = t("result.win")
            else:
                result_label = t("result.loss")

            finished_battles.append(
                {
                    "id": battle["id"],
                    "opponent_name": opponent_name,
                    "result_label": result_label,
                    "your_score": your_score,
                    "opponent_score": opponent_score,
                    "created_at": format_datetime(battle["finished_at"] or battle["started_at"]),
                }
            )

        return render_template(
            "history.html",
            training_results=training_results,
            battle_results=finished_battles,
        )

    @app.route("/finish")
    def finish():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        level = session.get("level", "")
        mode = session.get("mode", "")
        tasks = session.get("tasks")
        user_answers = session.get("user_answers")
        current = session.get("current", 0)

        if tasks is None or user_answers is None:
            return redirect(url_for("profile"))

        training_mode = session.get("training_mode", False)
        remaining_seconds = None if training_mode else get_remaining_seconds(session, app.config["TIME_LIMITS"])
        if remaining_seconds == 0:
            session["time_expired"] = True

        time_expired = False if training_mode else session.get("time_expired", False)
        is_completed = current >= len(tasks)

        if not is_completed and not time_expired:
            return redirect(url_for("task"))

        rows = []
        score = 0

        for index, task_row in enumerate(tasks):
            correct = task_row["a"]
            user_answer = user_answers[index] if index < len(user_answers) else None
            is_correct = user_answer == correct
            if is_correct:
                score += 1

            rows.append(
                {
                    "num": index + 1,
                    "question": task_row["q"],
                    "user_answer": user_answer,
                    "correct_answer": correct,
                    "is_correct": is_correct,
                }
            )

        total = len(tasks)
        percent = round((score / total) * 100) if total else 0
        section = "logic" if mode == "logic" else "math"
        time_limit = session.get("time_limit")
        time_spent = t("common.without_timer")

        if not training_mode and time_limit:
            elapsed_seconds = min(get_elapsed_seconds(session), time_limit)
            time_spent = format_seconds(elapsed_seconds)

        if not session.get("result_saved", False):
            save_result(section, level, mode, score, total, percent, current_user["id"])
            session["result_saved"] = True

        return render_template(
            "finish.html",
            rows=rows,
            score=score,
            total=total,
            percent=percent,
            level=level,
            mode=mode,
            time_spent=time_spent,
            time_limit=format_seconds(time_limit) if time_limit else None,
            time_expired=time_expired,
            training_mode=training_mode,
        )

    @app.route("/reset")
    def reset():
        clear_game_session(session)
        if get_current_user():
            return redirect(url_for("profile"))
        return redirect(url_for("home"))

    @app.route("/math")
    def math_page():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))
        return render_template("math.html")

    @app.route("/logic")
    def logic_page():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))
        return render_template("logic.html")

    @app.route("/stats")
    def stats():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        overall_stats = build_overall_stats(current_user["id"])
        best_learning_by_level = {
            "math": {
                level: format_best_row(get_best_result_by_section_and_level("math", level, current_user["id"]))
                for level in ("easy", "medium", "hard")
            },
            "logic": {
                level: format_best_row(get_best_result_by_section_and_level("logic", level, current_user["id"]))
                for level in ("easy", "medium", "hard")
            },
        }
        section_counts = get_attempts_count_by_section(current_user["id"])
        level_counts = get_attempts_count_by_level(current_user["id"])
        last_results = [format_result_row(row) for row in get_last_results(5, current_user["id"])]

        return render_template(
            "stats.html",
            total_attempts=overall_stats["total_activities"],
            avg_percent=overall_stats["overall_accuracy"],
            best_learning_by_level=best_learning_by_level,
            section_counts=section_counts,
            level_counts=level_counts,
            last_results=last_results,
            training_attempts=overall_stats["training_attempts"],
            battle_matches=overall_stats["battle_matches"],
            battle_wins=overall_stats["battle_wins"],
            battle_losses=overall_stats["battle_losses"],
            battle_draws=overall_stats["battle_draws"],
            player_name=current_user["name"],
        )

    @app.route("/profile")
    def profile():
        current_user = require_current_user()
        if not current_user:
            return redirect(url_for("home"))

        battle_stats = build_profile_battle_stats(current_user["id"], current_user)
        leaderboards = build_profile_leaderboards(current_user["id"])
        dashboard = build_profile_dashboard(current_user["id"])

        return render_template(
            "profile.html",
            player=current_user,
            battle_stats=battle_stats,
            leaderboards=leaderboards,
            dashboard=dashboard,
            profile_error=None,
        )

    @app.route("/admin/reset-all-data", methods=["POST"])
    def reset_all_data():
        clear_all_app_data()
        session.clear()
        return redirect(url_for("home"))
