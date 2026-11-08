import pytest
from pydantic import ValidationError

from tests.evals.cases import load_cases, parse_cases


def case(**overrides):
    base = {"id": "c1", "prompt": "1+1", "checks": {"expect_tools": ["add_numbers"]}}
    return {**base, **overrides}


def test_valid_case_defaults():
    [c] = parse_cases([case()])
    assert c.agent == "math" and c.tags == [] and c.checks.expect_tools == ["add_numbers"]


def test_unknown_check_name_is_rejected():
    with pytest.raises(ValidationError, match="expect_tool"):
        parse_cases([case(checks={"expect_tool": ["add_numbers"]})])


def test_unknown_case_field_is_rejected():
    with pytest.raises(ValidationError):
        parse_cases([case(promt="typo")])


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate case ids"):
        parse_cases([case(), case()])


@pytest.mark.parametrize("missing", ["id", "prompt", "checks"])
def test_missing_required_fields_are_rejected(missing):
    item = case()
    del item[missing]
    with pytest.raises(ValidationError):
        parse_cases([item])


def test_empty_checks_are_rejected():
    with pytest.raises(ValidationError, match="at least one check"):
        parse_cases([case(checks={})])


def test_bad_id_and_empty_prompt_are_rejected():
    with pytest.raises(ValidationError):
        parse_cases([case(id="Has Space")])
    with pytest.raises(ValidationError):
        parse_cases([case(prompt="")])


def test_top_level_must_be_a_list():
    with pytest.raises(TypeError, match="list"):
        parse_cases({"id": "c1"})


def test_load_cases_from_file(tmp_path):
    f = tmp_path / "cases.yaml"
    f.write_text(
        "- id: add\n  prompt: one plus one\n  tags: [add]\n"
        "  checks:\n    expect_tools: [add_numbers]\n    answer_contains_any: ['2']\n"
    )
    [c] = load_cases(f)
    assert c.id == "add" and c.tags == ["add"] and c.checks.answer_contains_any == ["2"]
