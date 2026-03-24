import json
import random
import re
from urllib import error, request

from app.services.battle_service import calculate_answer_score, get_bot_answer_data


def _task_category(task):
    question = str(task.get("q", "")).lower()
    if "лишнее" in question or "артық" in question or "odd" in question:
        return "odd_one_out"
    if any(token in question for token in ["последователь", "прогресс", "sequence", "тізбек"]):
        return "sequence"
    if "*" in question or "/" in question or "×" in question or "÷" in question:
        return "math_muldiv"
    if "+" in question or "-" in question:
        return "math_addsub"
    return "logic"


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def _level_accuracy_for_task(level_code, level_config, task):
    base = float(level_config["accuracy"])
    category = _task_category(task)

    adjustments = {
        "easy": {
            "math_addsub": 0.08,
            "math_muldiv": -0.04,
            "sequence": -0.10,
            "odd_one_out": -0.14,
            "logic": -0.08,
        },
        "medium": {
            "math_addsub": 0.05,
            "math_muldiv": 0.0,
            "sequence": -0.04,
            "odd_one_out": -0.08,
            "logic": -0.03,
        },
        "hard": {
            "math_addsub": 0.04,
            "math_muldiv": 0.03,
            "sequence": 0.0,
            "odd_one_out": -0.03,
            "logic": -0.01,
        },
    }

    adjusted = base + adjustments.get(level_code, {}).get(category, 0.0)
    return _clamp(adjusted, 0.2, 0.98)


def _build_prompt(task, level_code, language="ru"):
    options = task.get("options", [])
    options_text = ", ".join(str(option) for option in options)

    if language == "kk":
        return (
            f"Сен {level_code} деңгейіндегі AI қарсылассың. "
            "Төмендегі сұрақты шешіп, тек бір бүтін санды қайтар. "
            "Түсіндірме, сөз, тыныс белгісі жазба.\n"
            f"Сұрақ: {task['q']}\n"
            f"Жауап нұсқалары: {options_text}\n"
            "Тек бір сан қайтар."
        )

    if language == "en":
        return (
            f"You are an AI opponent at {level_code} difficulty. "
            "Solve the task below and return only one integer answer. "
            "Do not include explanations, words, or punctuation.\n"
            f"Question: {task['q']}\n"
            f"Options: {options_text}\n"
            "Return one number only."
        )

    return (
        f"Ты AI-соперник уровня {level_code}. "
        "Реши задачу и верни только один целый числовой ответ. "
        "Без объяснений, без слов, без знаков препинания.\n"
        f"Задача: {task['q']}\n"
        f"Варианты ответа: {options_text}\n"
        "Верни только одно число."
    )


def _extract_model_text(payload):
    candidates = payload.get("candidates", [])
    if not candidates:
        return ""
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    chunks = []
    for part in parts:
        text = part.get("text")
        if text:
            chunks.append(text)
    return " ".join(chunks).strip()


def _extract_answer_value(text, options):
    if not text:
        return None

    available = {int(option) for option in options}
    values = re.findall(r"-?\d+", text)
    for raw in values:
        value = int(raw)
        if value in available:
            return value
    return int(values[0]) if values else None


def _pick_wrong_answer(task):
    options = [int(option) for option in task.get("options", []) if int(option) != int(task["a"])]
    if options:
        return random.choice(options)
    correct = int(task["a"])
    candidates = [correct - 2, correct - 1, correct + 1, correct + 2]
    filtered = [item for item in candidates if item != correct]
    return random.choice(filtered) if filtered else correct + 1


def pick_ai_delay(level_config, task=None, level_code=None):
    min_time = float(level_config["min_time"])
    max_time = float(level_config["max_time"])

    if task and level_code:
        category = _task_category(task)
        if level_code == "easy":
            if category in ("sequence", "odd_one_out", "logic"):
                min_time += 1.5
                max_time += 3.0
            elif category == "math_muldiv":
                min_time += 0.8
                max_time += 1.8
        elif level_code == "medium":
            if category in ("sequence", "odd_one_out", "logic"):
                min_time += 0.6
                max_time += 1.4
        elif level_code == "hard":
            if category == "math_addsub":
                min_time = max(1.2, min_time - 0.4)
                max_time = max(min_time + 0.5, max_time - 0.5)
            elif category == "math_muldiv":
                min_time = max(1.4, min_time - 0.2)

    return round(random.uniform(min_time, max_time), 2)


def request_gemini_answer(task, api_key, model_name, language="ru", timeout=8):
    if not api_key:
        return None

    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": "Return only one integer taken from the answer options."
                }
            ]
        },
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_prompt(task, task.get("level", "medium"), language)
                    }
                ]
            }
        ],
        "generationConfig": {
            "thinkingConfig": {
                "thinkingLevel": "low"
            }
        },
    }

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    model_text = _extract_model_text(data)
    return _extract_answer_value(model_text, task.get("options", []))


def get_gemini_answer_data(task, level_code, level_config, api_key, model_name, language="ru", response_seconds=None):
    task_with_level = dict(task)
    task_with_level["level"] = level_code

    ai_answer = request_gemini_answer(task_with_level, api_key, model_name, language)
    if ai_answer is None:
        return get_bot_answer_data(level_config, task["a"])

    if response_seconds is None:
        response_seconds = pick_ai_delay(level_config, task, level_code)
    should_be_correct = random.random() <= _level_accuracy_for_task(level_code, level_config, task)
    correct_answer = int(task["a"])

    if should_be_correct:
        final_answer = correct_answer
        is_correct = True
    else:
        final_answer = _pick_wrong_answer(task)
        is_correct = False

    if ai_answer in task.get("options", []):
        if should_be_correct and ai_answer == correct_answer:
            final_answer = ai_answer
            is_correct = True
        elif not should_be_correct and ai_answer != correct_answer:
            final_answer = ai_answer
            is_correct = False

    return {
        "answer": final_answer,
        "response_seconds": response_seconds,
        "score": calculate_answer_score(is_correct, response_seconds),
        "is_correct": is_correct,
    }
