def deduplicate_rows(rows):
    unique = {}
    for row in rows:
        key = (row["url"], row["sheet_name"])
        if key in unique:
            existing = unique[key]
            combined = dict(existing)
            combined["full"] += row["full"]
            combined["partial"] += row["partial"]
            combined["eq_full"] = int(combined["full"] + 0.5 * combined["partial"])
            combined["total_bw"] += float(row.get("total_bw", 0) or 0)
            combined["avg_bw"] = (float(existing.get("avg_bw", 0)) + float(row.get("avg_bw", 0))) / 2
            unique[key] = combined
        else:
            unique[key] = row
    return list(unique.values())
