import pytest

from tests.evals.scoring import score_case

FAIL = ["answer_contains_any: none of ['2'] in answer: 'no'"]


def test_all_repeats_pass():
    r = score_case("add", [[], [], []], 1.0)
    assert r.passed and r.pass_rate == 1.0 and r.passed_repeats == 3 and r.failures == []


def test_two_of_three_fails_at_100_percent_with_the_failing_reason():
    r = score_case("add", [[], FAIL, []], 1.0)
    assert not r.passed and r.passed_repeats == 2
    assert [(f.repeat, f.reasons) for f in r.failures] == [(2, FAIL)]
    assert "repeat 2" in r.failure_text() and FAIL[0] in r.failure_text()


def test_two_of_three_passes_at_60_percent():
    r = score_case("add", [[], FAIL, []], 0.6)
    assert r.passed and round(r.pass_rate, 2) == 0.67


def test_single_repeat_and_all_failing():
    assert score_case("x", [[]], 1.0).passed
    r = score_case("x", [FAIL, FAIL], 0.5)
    assert not r.passed and r.pass_rate == 0 and len(r.failures) == 2


def test_threshold_boundary_is_inclusive():
    assert score_case("x", [[], FAIL], 0.5).passed


def test_no_repeats_is_an_error():
    with pytest.raises(ValueError):
        score_case("x", [], 1.0)


def test_summary_line():
    assert score_case("add", [[], FAIL, []], 1.0).summary() == "add: 2/3 passed (67%)"
