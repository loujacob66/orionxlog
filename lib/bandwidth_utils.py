def sanitize_bandwidth(value):
    try:
        return float(str(value).strip().replace("MB", "").strip())
    except:
        return 0.0
