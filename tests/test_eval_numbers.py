"""The numeric answer check: values are compared, never text. No model is involved."""

import pytest
from langchain_core.messages import AIMessage

from tests.evals.harness import Checks, extract_trace, run_checks
from tests.evals.numbers import has_word, number_tokens, readings, states_number

ACCEPT = [
    (2, "The answer is 2."), (2, "1 + 1 = 2"),
    (3500, "3,500"), (3500, "3.500"), (3500, "3 500"), (3500, "3 500"), (3500, "3500"),
    (3500, "That is 3 500 dollars."),
    (6.25, "6,25"), (6.25, "6.25"),
    (1024, "1,024"), (1024, "1.024"), (1024, "1 024"), (1024, "1024"),
    (-2, "-2"), (-2, "−2"), (-2, "The result is -2."),
    (42, "6 times 7 is 42."), (42, "It is 42, and then some."), (42, "42."),
    (80779853376, "80,779,853,376"), (80779853376, "80.779.853.376"), (80779853376, "80 779 853 376"),
    (80779853376, "80779853376"),
    (660, "660 metres"), (330, "It is 330 metres (1,083 ft) tall."), (1083, "330 metres (1,083 feet)"),
    (7, "10 minus 3 is 7"), (7, "7."), (20, "(2 + 3) * 4 = 20"), (6.25, "25 divided by 4 is 6.25."),
    (2, "Version 2 is out"), (1234.56, "1.234,56"), (1234.56, "1,234.56"),
]

REJECT = [
    # the demonstrated false positives: the digits are there, the number is not
    (2, "The answer is 12."), (2, "Hasilnya adalah 20."), (2, "22"), (2, "It is 2nd"), (2, "page 12 of 20"),
    (2, "-2"), (-2, "2"),
    (3500, "35,000"), (3500, "350"), (42, "142"), (42, "4.2"), (7, "17"), (7, "70"),
    (6.25, "625"), (1024, "10,240"), (660, "6600"), (20, "2020"),
    # a separator only groups thousands in groups of exactly three digits
    (625, "6,25"), (35, "3.5"), (35, "3,5"), (1234, "1,23"), (12345, "1,234,5"), (1, "1.0.0"),
    (2, "no numbers here"), (2, ""),
]


@pytest.mark.parametrize(("value", "text"), ACCEPT)
def test_numbers_that_are_stated(value, text):
    assert states_number(text, value), f"{text!r} should state {value}"


@pytest.mark.parametrize(("value", "text"), REJECT)
def test_numbers_that_are_not_stated(value, text):
    assert not states_number(text, value), f"{text!r} must not state {value}"


def test_ambiguous_tokens_have_every_well_formed_reading():
    assert readings("3.500") == {3.5, 3500.0}
    assert readings("1,024") == {1.024, 1024.0}
    assert readings("6,25") == {6.25}
    assert readings("4.2") == {4.2}
    assert readings("1.234,56") == {1234.56}
    assert readings("80.779.853.376") == {80779853.376, 80779853376.0}
    assert readings("12") == {12.0}


def test_tokens_report_the_text_found():
    assert [text for text, _ in number_tokens("1,083 ft and 330 m, minus -4.")] == ["1,083", "330", "-4"]


# --- whole-word alternatives


def test_whole_word_alternatives():
    assert has_word("Satu ditambah satu sama dengan dua.", ["dua"])
    assert has_word("DUA", ["dua"])
    assert not has_word("duapuluh", ["dua"])
    assert not has_word("dua-belas", []) and not has_word("", ["dua"])
    assert has_word("minus 2", ["minus 2", "negative 2"])


# --- through run_checks


def failures(checks: dict, answer: str):
    trace = extract_trace([AIMessage(answer)])
    return run_checks(Checks(**checks), trace)


def test_the_demonstrated_wrong_answers_for_the_two_indonesian_style_checks_are_rejected():
    checks = {"answer_number": [{"value": 2, "words": ["dua"]}], "answer_excludes": ["belas", "puluh", "ratus"]}
    assert failures(checks, "Satu ditambah satu sama dengan dua.") == []
    assert failures(checks, "Hasilnya 2.") == []
    for wrong in ("Satu ditambah satu sama dengan dua belas.", "The answer is 12.", "Hasilnya adalah 20."):
        assert failures(checks, wrong), f"{wrong!r} must fail"


def test_failure_message_shows_the_expected_number_and_what_the_answer_states():
    [message] = failures({"answer_number": [{"value": 3500}]}, "That makes 35,000 in total.")
    assert "answer_number: expected 3500" in message
    assert "'35,000'" in message and "That makes 35,000" in message


def test_failure_message_mentions_the_word_alternatives():
    [message] = failures({"answer_number": [{"value": 2, "words": ["dua"]}]}, "tiga")
    assert "'dua'" in message


def test_every_entry_must_be_satisfied():
    checks = {"answer_number": [{"value": 330}, {"value": 660}]}
    assert failures(checks, "It is 330 m tall; doubled that is 660.") == []
    [message] = failures(checks, "It is 330 m tall.")
    assert "expected 660" in message


def test_the_check_counts_as_a_check_for_the_case_loader():
    assert not Checks(answer_number=[{"value": 1}]).is_empty()
