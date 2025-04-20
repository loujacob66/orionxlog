
from datetime import datetime

def extract_consumed_date(sheet_name):
    try:
        sheet_name = str(sheet_name).strip()
        if sheet_name.isdigit():
            return f"{sheet_name}-01-01"
        if "/" in sheet_name:
            # assume MM/YYYY or MM/YYYY format
            parts = sheet_name.split("/")
            if len(parts) == 2:
                month, year = parts
                return f"{year}-{int(month):02d}-01"
        # fallback
        return None
    except:
        return None
