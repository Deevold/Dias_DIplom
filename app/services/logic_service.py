import random


def _logic_prompt(kind, language="ru"):
    prompts = {
        "sequence": {
            "ru": "Продолжите последовательность: ",
            "kk": "Тізбекті жалғастырыңыз: ",
            "en": "Continue the sequence: ",
        },
        "odd": {
            "ru": "Найдите лишнее число: ",
            "kk": "Артық санды табыңыз: ",
            "en": "Find the odd number: ",
        },
    }
    return prompts.get(kind, prompts["sequence"]).get(language, prompts["sequence"]["ru"])


def generate_logic_task(level, language="ru"):
    if level == "easy":
        start = random.randint(1, 10)
        step = random.randint(2, 4)
        seq = [start + i * step for i in range(5)]
        answer = seq[-1]
        seq[-1] = "?"
        question = _logic_prompt("sequence", language) + " ".join(map(str, seq))
        return {"q": question, "a": answer}

    if level == "medium":
        task_type = random.choice(["arithmetic", "geometric"])

        if task_type == "arithmetic":
            start = random.randint(1, 15)
            step = random.randint(2, 6)
            seq = [start + i * step for i in range(5)]
            answer = seq[-1]
            seq[-1] = "?"
            question = _logic_prompt("sequence", language) + " ".join(map(str, seq))
            return {"q": question, "a": answer}

        start = random.randint(1, 5)
        multiplier = random.randint(2, 3)
        seq = [start * (multiplier ** i) for i in range(5)]
        answer = seq[-1]
        seq[-1] = "?"
        question = _logic_prompt("sequence", language) + " ".join(map(str, seq))
        return {"q": question, "a": answer}

    if level == "hard":
        task_type = random.choice(["arithmetic", "geometric", "difference", "odd_one_out"])

        if task_type == "arithmetic":
            start = random.randint(1, 20)
            step = random.randint(3, 7)
            seq = [start + i * step for i in range(5)]
            answer = seq[-1]
            seq[-1] = "?"
            question = _logic_prompt("sequence", language) + " ".join(map(str, seq))
            return {"q": question, "a": answer}

        if task_type == "geometric":
            start = random.randint(1, 5)
            multiplier = random.randint(2, 4)
            seq = [start * (multiplier ** i) for i in range(5)]
            answer = seq[-1]
            seq[-1] = "?"
            question = _logic_prompt("sequence", language) + " ".join(map(str, seq))
            return {"q": question, "a": answer}

        if task_type == "difference":
            start = random.randint(1, 10)
            diff = random.randint(2, 4)
            seq = [start]
            current = start

            for index in range(1, 5):
                current += diff + (index - 1)
                seq.append(current)

            answer = seq[-1]
            seq[-1] = "?"
            question = _logic_prompt("sequence", language) + " ".join(map(str, seq))
            return {"q": question, "a": answer}

        subtype = random.choice(["divisible", "parity"])

        if subtype == "divisible":
            divisor = random.randint(2, 5)
            correct_numbers = random.sample([divisor * value for value in range(1, 11)], 3)

            wrong = random.randint(1, 20)
            while wrong % divisor == 0 or wrong in correct_numbers:
                wrong = random.randint(1, 20)

            numbers = correct_numbers + [wrong]
            random.shuffle(numbers)

            question = _logic_prompt("odd", language) + " ".join(map(str, numbers))
            return {"q": question, "a": wrong, "options": numbers}

        even_mode = random.choice([True, False])

        if even_mode:
            correct_numbers = random.sample(list(range(2, 21, 2)), 3)
            wrong = random.choice(list(range(1, 20, 2)))
        else:
            correct_numbers = random.sample(list(range(1, 20, 2)), 3)
            wrong = random.choice(list(range(2, 21, 2)))

        while wrong in correct_numbers:
            if even_mode:
                wrong = random.choice(list(range(1, 20, 2)))
            else:
                wrong = random.choice(list(range(2, 21, 2)))

        numbers = correct_numbers + [wrong]
        random.shuffle(numbers)

        question = _logic_prompt("odd", language) + " ".join(map(str, numbers))
        return {"q": question, "a": wrong, "options": numbers}

    return None


def generate_logic_tasks(level, tasks_count, language="ru"):
    valid_levels = {"easy", "medium", "hard"}
    if level not in valid_levels:
        return None

    return [generate_logic_task(level, language) for _ in range(tasks_count)]
