import re

def normalize_url(url):
    return str(url).strip().lower()

def extract_url_from_cell(cell_value):
    match = re.search(r'(https?://[^\s]+)', str(cell_value))
    return match.group(1) if match else str(cell_value)

def extract_title_from_url(url):
    return url.split("/")[-1].split(".")[0]
