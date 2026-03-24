import json
import random
from datetime import datetime, timedelta

from app.services.logic_service import generate_logic_task
from app.services.math_service import generate_task


def detect_math_operator(question_text):
    if not question_text:
        return None

    for operator in ("+", "-", "*", "/", "×", "÷", "Г—", "Г·"):
        if operator in question_text:
            return operator
    return None


def generate_answer_options(correct_answer, question_text=None):
    options = {correct_answer}
    distance = max(2, min(18, abs(correct_answer) // 3 + 3))
    operator = detect_math_operator(question_text)

    # For arithmetic tasks, especially multiplication/division, avoid the "only one
    # option ends with the correct digit" clue by generating distractors that may
    # share the same last digit.
    same_last_digit_target = 0
    if operator in ("*", "/", "×", "÷", "Г—", "Г·"):
        same_last_digit_target = 1

    attempts = 0
    while len(options) < 4 and attempts < 200:
        attempts += 1

        use_same_last_digit = same_last_digit_target > 0 and random.random() < 0.7
        if use_same_last_digit:
            tens_shift = random.randint(1, max(2, distance))
            direction = random.choice([-1, 1])
            candidate = correct_answer + direction * tens_shift * 10
        else:
            shift = random.randint(1, distance)
            direction = random.choice([-1, 1])
            candidate = correct_answer + shift * direction

        if candidate == correct_answer:
            continue
        if abs(candidate - correct_answer) > max(60, distance * 10):
            continue
        options.add(candidate)
        if candidate % 10 == correct_answer % 10 and same_last_digit_target > 0:
            same_last_digit_target -= 1

    while len(options) < 4:
        candidate = correct_answer + random.choice([-1, 1]) * random.randint(1, max(2, distance))
        if candidate != correct_answer:
            options.add(candidate)

    options_list = list(options)
    random.shuffle(options_list)
    return options_list


def decorate_battle_task(task):
    task_copy = dict(task)
    if "options" in task and task["options"]:
        task_copy["options"] = list(task["options"])
    else:
        task_copy["options"] = generate_answer_options(task["a"], task.get("q"))
    return task_copy


def get_task_signature(task):
    options = tuple(task.get("options", []))
    return task.get("q"), task.get("a"), options


def generate_battle_tasks(tasks_count, language="ru"):
    tasks = []
    used_signatures = set()

    for index in range(tasks_count):
        unique_task = None

        for _ in range(60):
            if index % 2 == 0:
                operation = random.choice(["+", "-", "*", "/"])
                if operation in ("*", "/"):
                    candidate = decorate_battle_task(generate_task(2, 20, ops=(operation,)))
                else:
                    candidate = decorate_battle_task(generate_task(1, 50, ops=(operation,)))
            else:
                logic_level = random.choice(["easy", "medium", "hard"])
                candidate = decorate_battle_task(generate_logic_task(logic_level, language))

            signature = get_task_signature(candidate)
            if signature not in used_signatures:
                used_signatures.add(signature)
                unique_task = candidate
                break

        if unique_task is None:
            unique_task = candidate

        tasks.append(unique_task)

    return tasks


def dumps_data(value):
    return json.dumps(value, ensure_ascii=False)


def loads_data(value, default):
    if not value:
        return default
    return json.loads(value)


def parse_battle_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def get_battle_deadline_datetime(started_at, time_limit):
    started_dt = parse_battle_datetime(started_at)
    return started_dt + timedelta(seconds=time_limit)


def get_battle_deadline_timestamp(started_at, time_limit):
    deadline_dt = get_battle_deadline_datetime(started_at, time_limit)
    return int(deadline_dt.timestamp())


def get_battle_remaining_seconds(started_at, time_limit):
    deadline_dt = get_battle_deadline_datetime(started_at, time_limit)
    remaining = int((deadline_dt - datetime.now()).total_seconds())
    return max(0, remaining)


def calculate_answer_score(is_correct, response_seconds, question_time=20, points_possible=1000):
    if not is_correct:
        return 0

    # Kahoot-style timing score:
    # round((1 - ((response_time / question_timer) / 2)) * points_possible)
    # We cap the fastest answers at the full points and use a 20-second battle question window.
    response_time = max(0.0, float(response_seconds))
    question_window = max(1.0, float(question_time))

    if response_time <= 0.5:
        return int(points_possible)

    ratio = min(response_time / question_window, 1.0)
    raw_score = (1 - (ratio / 2)) * points_possible
    return max(0, round(raw_score))


def calculate_progress(player_score, opponent_score):
    diff = player_score - opponent_score
    max_push = 6000
    progress = 50 + (diff / max_push) * 50
    return max(0, min(100, round(progress, 1)))


def is_pushout(player_score, opponent_score):
    progress = calculate_progress(player_score, opponent_score)
    return progress <= 0 or progress >= 100


def calculate_elo_change(score_diff):
    if score_diff >= 500:
        return 35
    if score_diff >= 350:
        return 32
    if score_diff >= 220:
        return 28
    if score_diff >= 120:
        return 24
    return 20


def get_bot_answer_data(bot_level, correct_answer):
    accuracy = bot_level["accuracy"]
    answer_time = random.randint(bot_level["min_time"], bot_level["max_time"])
    is_correct = random.random() <= accuracy

    if is_correct:
        answer = correct_answer
    else:
        wrong_options = [correct_answer - 2, correct_answer - 1, correct_answer + 1, correct_answer + 2]
        filtered = [item for item in wrong_options if item != correct_answer]
        answer = random.choice(filtered) if filtered else correct_answer + 1

    return {
        "answer": answer,
        "response_seconds": answer_time,
        "score": calculate_answer_score(is_correct, answer_time),
        "is_correct": is_correct,
    }


def get_bot_level_config(levels, code):
    return levels.get(code)


def get_current_battle_question(tasks, answers):
    current_index = len(answers)
    if current_index >= len(tasks):
        return None, current_index
    return tasks[current_index], current_index
