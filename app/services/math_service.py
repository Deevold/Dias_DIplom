import random


def generate_task(min_n, max_n, ops=("+", "-")):
    op = random.choice(list(ops))

    if op == "+":
        a = random.randint(min_n, max_n)
        b = random.randint(min_n, max_n)
        return {"q": f"{a} + {b}", "a": a + b}

    if op == "-":
        a = random.randint(min_n, max_n)
        b = random.randint(min_n, max_n)
        return {"q": f"{a} - {b}", "a": a - b}

    if op == "*":
        a = random.randint(min_n, max_n)
        b = random.randint(min_n, max_n)
        return {"q": f"{a} × {b}", "a": a * b}

    if op == "/":
        b = random.randint(max(2, min_n), max_n)
        answer = random.randint(min_n, max_n)
        a = b * answer
        return {"q": f"{a} ÷ {b}", "a": answer}

    a = random.randint(min_n, max_n)
    b = random.randint(min_n, max_n)
    return {"q": f"{a} + {b}", "a": a + b}


def generate_math_tasks(level, mode, tasks_count):
    settings = {
        "easy": {"addsub": (1, 10), "muldiv": (2, 10)},
        "medium": {"addsub": (1, 50), "muldiv": (2, 20)},
        "hard": {"addsub": (1, 200), "muldiv": (2, 50)},
    }

    if level not in settings:
        return None

    if mode == "mix":
        ops = ("+", "-", "*", "/")
    else:
        ops = ("+", "-")

    cfg = settings[level]
    tasks = []

    for _ in range(tasks_count):
        op = random.choice(list(ops))
        if op in ("*", "/"):
            min_n, max_n = cfg["muldiv"]
            tasks.append(generate_task(min_n, max_n, ops=(op,)))
        else:
            min_n, max_n = cfg["addsub"]
            tasks.append(generate_task(min_n, max_n, ops=(op,)))

    return tasks
