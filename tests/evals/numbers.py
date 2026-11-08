"""Find the numbers an answer states, comparing values and not text. No model is involved here.

A number may be written with thousands separators (`,` `.` or a space) and either decimal mark, so one
token can have more than one reading: `3.500` is 3500 or 3.5. Only well-formed readings count, which is
what keeps `4.2` from meaning 42 and `6,25` from meaning 625.
"""

import math
import re

# Digits grouped by , . or a space (thousands) with an optional decimal part, or plain digits with an
# optional decimal part. A token may not touch a word character or continue as `.digit` / `,digit`, so the
# 2 in `12`, `20`, `2nd` or `1.0.0` is never a match and a trailing full stop is not part of the number.
_GROUPED = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?"
_PLAIN = r"\d+(?:[.,]\d+)?"
_TOKEN = re.compile(rf"(?<![\w.,])(?P<neg>[-−])?(?P<num>{_GROUPED}|{_PLAIN})(?![\w]|[.,]\d)")

_REL_TOL = 1e-9


def readings(token: str) -> set[float]:
    """Every value a written (unsigned) number could mean."""
    stripped = re.sub(r"[  ]", "", token)  # spaces only ever group thousands
    parts = re.split(r"[.,]", stripped)
    if len(parts) == 1:
        return {float(stripped)}
    found = set()
    first, rest = parts[0], parts[1:]
    if 1 <= len(first) <= 3 and all(len(p) == 3 for p in rest):
        found.add(float("".join(parts)))  # thousands reading: 3.500 -> 3500
    head, tail = parts[:-1], parts[-1]
    if all(len(p) == 3 for p in head[1:]) and (len(head) == 1 or 1 <= len(head[0]) <= 3):
        found.add(float("".join(head) + "." + tail))  # decimal reading: the last separator is the mark
    return found


def number_tokens(text: str) -> list[tuple[str, set[float]]]:
    """The numbers in `text`, each as the text found and the values it could mean (sign applied)."""
    tokens = []
    for match in _TOKEN.finditer(text):
        sign = -1 if match.group("neg") else 1
        tokens.append((match.group(0), {sign * v for v in readings(match.group("num"))}))
    return tokens


def states_number(text: str, value: float) -> bool:
    return any(
        math.isclose(v, value, rel_tol=_REL_TOL, abs_tol=_REL_TOL)
        for _, values in number_tokens(text)
        for v in values
    )


def has_word(text: str, words: list[str]) -> bool:
    """True if any of `words` appears as a whole word (or phrase), ignoring case."""
    return any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) for word in words)
