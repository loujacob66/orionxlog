from collections import defaultdict
import numpy as np

def deduplicate_rows(rows):
    merged = {}
    duplicates = []

    for row in rows:
        key = (row['url'], row['sheet_name'])
        if key in merged:
            existing = merged[key]
            existing['full'] += row['full']
            existing['partial'] += row['partial']
            existing['total_bw'] += row['total_bw']
            existing['avg_bw_values'].append(row['avg_bw'] or 0.0)
            duplicates.append(row)
        else:
            merged[key] = {
                'url': row['url'],
                'sheet_name': row['sheet_name'],
                'full': row['full'],
                'partial': row['partial'],
                'total_bw': row['total_bw'],
                'avg_bw_values': [row['avg_bw'] or 0.0]
            }

    deduped_rows = []
    for key, data in merged.items():
        avg_bw = np.mean(data['avg_bw_values']) if data['avg_bw_values'] else 0.0
        deduped_rows.append({
            'url': data['url'],
            'sheet_name': data['sheet_name'],
            'full': data['full'],
            'partial': data['partial'],
            'avg_bw': round(avg_bw, 2),
            'total_bw': round(data['total_bw'], 2),
        })

    return deduped_rows, duplicates
