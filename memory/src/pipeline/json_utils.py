"""
Shared JSON parsing utilities.

Centralizes the JSON response parsing logic that was previously
duplicated across pass1_narrative.py, pass2_data.py, synthesizer.py, and edge_builder.py.
"""

import json
import re


def parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks and truncation.
    
    Handles:
    - Markdown ```json ... ``` code fences
    - Bare JSON objects
    - Truncated JSON (attempts basic repair)
    
    Returns empty dict on failure.
    """
    if not raw:
        return {}

    cleaned = raw.strip()

    # Strip markdown code fence if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)

    # Try parsing directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try extracting a JSON object via regex
    match = re.search(r'\{[\s\S]+\}', cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Attempt repair for truncated JSON
    try:
        repaired = cleaned
        open_quotes = cleaned.count('"') % 2
        if open_quotes:
            repaired += '"'
        
        open_brackets = repaired.count('[') - repaired.count(']')
        open_braces = repaired.count('{') - repaired.count('}')
        
        repaired += ']' * max(0, open_brackets)
        repaired += '}' * max(0, open_braces)

        return json.loads(repaired)
    except (json.JSONDecodeError, Exception):
        pass

    return {}
