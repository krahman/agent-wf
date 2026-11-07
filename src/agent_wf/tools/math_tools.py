import re
import time

import requests
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import tool
from wikipedia import wikipedia as wp

NUMBER_PATTERN = r"-?\d+(?:\.\d+)?"


def extract_numbers(text: str) -> list[float]:
    return [float(num) for num in re.findall(NUMBER_PATTERN, text)]


@tool
def add_numbers(inputs: str) -> dict:
    """Adds all numeric values found in the input string, e.g. "10, 20 and 30"."""
    return {"result": sum(extract_numbers(inputs))}


@tool
def subtract_numbers(inputs: str) -> dict:
    """
    Extracts numbers from a string and subtracts each number after the first from the first,
    i.e. inputs[0] - inputs[1] - inputs[2] ...

    Example Input: "100, 20, 10"
    Example Output: {"result": 70}
    """
    numbers = extract_numbers(inputs)
    if not numbers:
        return {"result": 0}

    result = numbers[0]
    for num in numbers[1:]:
        result -= num
    return {"result": result}


@tool
def multiply_numbers(inputs: str) -> dict:
    """Extracts numbers from a string and calculates their product."""
    numbers = extract_numbers(inputs)
    if not numbers:
        return {"result": 1}

    result = 1.0
    for num in numbers:
        result *= num
    return {"result": result}


@tool
def divide_numbers(inputs: str) -> dict:
    """Extracts numbers from a string and divides the first by each subsequent number."""
    numbers = extract_numbers(inputs)
    if not numbers:
        return {"result": 0}

    if any(num == 0 for num in numbers[1:]):
        return {"result": "Cannot divide by zero."}

    result = numbers[0]
    for num in numbers[1:]:
        result /= num
    return {"result": result}


@tool
def power_tool(input_text: str) -> dict:
    """
    Calculates the power of a number (x^y). Input is a string containing the base
    followed by the exponent, e.g. "2, 3", "5^2" or "2 to the power of 3".
    """
    numbers = extract_numbers(input_text)
    if len(numbers) != 2:
        return {"result": "Invalid input. Please provide exactly two numbers: a base and an exponent."}

    base, exponent = numbers
    try:
        return {"result": base**exponent}
    except (ZeroDivisionError, OverflowError) as e:
        return {"result": f"Error during calculation: {e}"}


wp.API_URL = "https://en.wikipedia.org/w/api.php"


def _patched_request(params, _retries=3):
    params["format"] = "json"
    params.setdefault("action", "query")
    headers = {"User-Agent": "agent_wf/0.1.0"}

    last_exc = None
    for _ in range(_retries):
        r = requests.get(wp.API_URL, params=params, headers=headers)
        try:
            return r.json()
        except ValueError as e:
            last_exc = e
            time.sleep(1)
    raise last_exc


wp._wiki_request = _patched_request


@tool
def search_wikipedia(query: str) -> str:
    """Search Wikipedia for factual information about a topic and return a summary."""
    return WikipediaAPIWrapper().run(query)


math_tools = [add_numbers, subtract_numbers, multiply_numbers, divide_numbers, power_tool]
all_tools = [*math_tools, search_wikipedia]
