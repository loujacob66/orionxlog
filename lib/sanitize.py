import re

def sanitize_bandwidth(value):
    if isinstance(value, str):
        match = re.search(r"[\d.]+", value)
        return float(match.group()) if match else 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
