import pytest
from pydantic import ValidationError

from agent_wf.tools.math import (
    add_numbers,
    divide_numbers,
    power_tool,
    subtract_numbers,
)


def test_subtract_with_negative_and_hyphen_free_input():
    assert subtract_numbers.invoke({"numbers": [10, 3]}) == {"result": 7}
    assert subtract_numbers.invoke({"numbers": [100, 20, 10]}) == {"result": 70}


def test_add_large_and_decimal_values():
    assert add_numbers.invoke({"numbers": [1000, 0.5]}) == {"result": 1000.5}


def test_divide_by_zero_returns_error_not_result():
    out = divide_numbers.invoke({"numbers": [5, 0]})
    assert "error" in out and "result" not in out


def test_power_errors():
    assert power_tool.invoke({"base": 2, "exponent": 3}) == {"result": 8}
    assert "error" in power_tool.invoke({"base": 0, "exponent": -1})
    assert "error" in power_tool.invoke({"base": -8, "exponent": 0.5})


def test_empty_numbers_rejected():
    with pytest.raises(ValidationError):
        add_numbers.invoke({"numbers": []})
