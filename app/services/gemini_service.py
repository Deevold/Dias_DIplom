import json
import random
import re
from urllib import error, request

from app.services.battle_service import calculate_answer_score, get_bot_answer_data


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


def pick_ai_delay(level_config):
    return random.randint(level_config["min_time"], level_config["max_time"])


def request_gemini_answer(task, api_key, model_name, language="ru", timeout=5):
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
        response_seconds = pick_ai_delay(level_config)
    should_be_correct = random.random() <= level_config["accuracy"]
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
