"""Multiple-choice steps.

A quiz/practice step becomes multiple choice automatically when
- its text lists questions as "Question 1. ..." followed by options "A) ...", "B) ...", and
- its Resource holds the answer key, e.g. "Answer key: 1-A, 2-D, 3-C".

Students then pick an option per question instead of typing an answer. The
choice is checked at once, saved as "1-A, 2-D, 3-C" (same format as the key),
and afterwards the student sees every question with their choice and the
correct answer, so they can review their mistakes.
"""
import re

QUESTION_RE = re.compile(r"^\s*Question\s+(\d+)\s*[.)]\s*(.*)$", re.IGNORECASE)
OPTION_RE = re.compile(r"^\s*([A-H])\)\s*(.*)$")
PAIR_RE = re.compile(r"(\d+)\s*[-–:.)]\s*([A-Ha-h])\b")
INSTRUCTION_RE = re.compile(r"^\s*Write your answers like this", re.IGNORECASE)


def parse_pairs(text):
    """'1-A, 2-D, 3-C' -> {1: 'A', 2: 'D', 3: 'C'}"""
    return {int(n): letter.upper() for n, letter in PAIR_RE.findall(text or "")}


def format_pairs(pairs):
    return ", ".join(f"{n}-{pairs[n]}" for n in sorted(pairs))


def parse_mcq(body, key_text):
    """Returns {'intro', 'questions', 'key'} or None if this isn't a complete multiple-choice step."""
    intro, questions, current = [], [], None
    for line in (body or "").splitlines():
        q = QUESTION_RE.match(line)
        o = OPTION_RE.match(line)
        if q:
            current = {"number": int(q.group(1)), "text": q.group(2).strip(), "options": []}
            questions.append(current)
        elif current is None:
            if not INSTRUCTION_RE.match(line):
                intro.append(line)
        elif o:
            current["options"].append({"letter": o.group(1), "text": o.group(2).strip()})
        elif line.strip() and not current["options"]:
            current["text"] = (current["text"] + " " + line.strip()).strip()
    key = parse_pairs(key_text)
    if not questions:
        return None
    for q in questions:
        letters = [o["letter"] for o in q["options"]]
        if len(letters) < 2 or key.get(q["number"]) not in letters:
            return None
    while intro and intro[-1].strip() in ("", "—", "-", "--", "---"):
        intro.pop()
    return {"intro": "\n".join(intro).strip(), "questions": questions, "key": key}


def grade(mcq, chosen):
    """chosen: {1: 'A', ...}. Returns (score, total, results) - results is the question list with
    'chosen', 'correct', 'is_right' added, and per option 'is_chosen' / 'is_correct'."""
    results, score = [], 0
    for q in mcq["questions"]:
        correct = mcq["key"][q["number"]]
        mine = chosen.get(q["number"])
        right = mine == correct
        score += right
        results.append({
            **q, "chosen": mine, "correct": correct, "is_right": right,
            "options": [{**o, "is_chosen": o["letter"] == mine, "is_correct": o["letter"] == correct}
                        for o in q["options"]],
        })
    return score, len(mcq["questions"]), results
