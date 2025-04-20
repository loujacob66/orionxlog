def normalize_header(header: str) -> str:
    return header.strip().lower() if isinstance(header, str) else ''

def get_column_mapping(headers):
    COLUMN_MAP = {
        'full': ['full', 'full ', 'Full', 'Full Downloads'],
        'partial': ['partial', 'Partial', 'Partial Downloads'],
        'avg_bw': ['avg_bw', 'Average Bandwidth', 'Avg BW'],
        'total_bw': ['total_bw', 'Total BW', 'Total Bandwidth']
    }
    normalized_headers = {normalize_header(h): h for h in headers}
    mapping = {}
    for internal_key, possible_names in COLUMN_MAP.items():
        for name in possible_names:
            if normalize_header(name) in normalized_headers:
                mapping[internal_key] = normalized_headers[normalize_header(name)]
                break
    return mapping
