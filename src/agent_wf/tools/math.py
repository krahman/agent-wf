import math

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class NumbersArgs(BaseModel):
    numbers: list[float] = Field(min_length=1, description="Numbers to operate on, in order.")


class PowerArgs(BaseModel):
    base: float
    exponent: float


@tool(args_schema=NumbersArgs)
def add_numbers(numbers: list[float]) -> dict:
    """Add all the given numbers."""
    return {"result": sum(numbers)}


@tool(args_schema=NumbersArgs)
def subtract_numbers(numbers: list[float]) -> dict:
    """Subtract each number after the first from the first: numbers[0] - numbers[1] - ..."""
    first, *rest = numbers
    return {"result": first - sum(rest)}


@tool(args_schema=NumbersArgs)
def multiply_numbers(numbers: list[float]) -> dict:
    """Multiply all the given numbers together."""
    return {"result": math.prod(numbers)}


@tool(args_schema=NumbersArgs)
def divide_numbers(numbers: list[float]) -> dict:
    """Divide the first number by each subsequent number in turn."""
    first, *rest = numbers
    if any(n == 0 for n in rest):
        return {"error": "Cannot divide by zero."}
    result = first
    for n in rest:
        result /= n
    return {"result": result}


@tool(args_schema=PowerArgs)
def power_tool(base: float, exponent: float) -> dict:
    """Raise base to the power of exponent."""
    try:
        result = base**exponent
    except (ZeroDivisionError, OverflowError) as e:
        return {"error": f"Error during calculation: {e}"}
    if isinstance(result, complex):
        return {"error": "Result is not a real number."}
    return {"result": result}


math_tools = [add_numbers, subtract_numbers, multiply_numbers, divide_numbers, power_tool]
