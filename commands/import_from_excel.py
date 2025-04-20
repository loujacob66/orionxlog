import pandas as pd
import sqlite3
import os
import re
import math
from datetime import datetime
from argparse import ArgumentParser

def extract_code(url):
    fname = url.split("/")[-1]
    match1 = re.search(r"/(\d{3})@", url)
    match2 = re.search(r"^(A\d{3})-", fname)
    if match1:
        return match1.group(1)
    elif match2:
        return match2.group(1)
    return None

def extract_feature(url):
    fname = url.split("/")[-1].lower()
    if "mktg_podcast" in fname:
        return "Mktg_podcast"
    elif "oxd" in fname:
        return "OXD"
    elif "hpcnb" in fname:
        return "HPCNB"
    elif "hpcpodcast" in fname:
        return "HPCpodcast"
    return None

def extract_title(url):
    fname = url.split("/")[-1]
    fname = re.sub(r"\.\w+$", "", fname)
    fname = re.sub(r"^\d{3}@", "", fname)
    fname = re.sub(r"^A\d{3}-", "", fname)
    for prefix in ["HPCpodcast_", "HPCNB_", "OXD_", "Mktg_Podcast_"]:
        fname = fname.replace(prefix, "")
    parts = fname.split("_")
    if len(parts) == 1 and re.match(r"\d{4}-\d{2}-\d{2}", parts[0]):
        feature = extract_feature(url)
        return f"{feature}_{parts[0]}" if feature else parts[0]
    return parts[0]

def extract_created_at(url):
    match = re.search(r"/(\d{4})/(\d{2})/", url)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)}-{match.group(2)}-01", "%Y-%m-%d").date()
        except ValueError:
            return None
    return None

def parse_float(val):
    if isinstance(val, str):
        val = val.replace("MB", "").replace("mb", "").strip()
    try:
        return float(val)
    except:
        return None

def import_from_excel(path, override=False, dry_run=False):
    db_path = "data/podcasts.db"
    if override and os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS podcasts (
            url TEXT,
            title TEXT,
            code TEXT,
            feature TEXT,
            full INTEGER,
            partial INTEGER,
            avg_bw REAL,
            total_bw REAL,
            eq_full INTEGER,
            created_at TEXT,
            consumed_at TEXT,
            imported_at TEXT,
            sheet_name TEXT,
            PRIMARY KEY (url, sheet_name)
        )
    """)
    conn.commit()

    xls = pd.ExcelFile(path)
    inserted, skipped, duplicates = 0, 0, 0
    dup_rows = []

    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        df.columns = [col.strip() for col in df.columns]
        if not {"URL", "Full", "Partial", "Avg BW", "Total BW"}.issubset(df.columns):
            continue

        df = df[df["URL"].str.contains("/wp-content/uploads", na=False)]

        for _, row in df.iterrows():
            try:
                url = row["URL"]
                full = pd.to_numeric(row["Full"], errors="coerce")
                partial = pd.to_numeric(row["Partial"], errors="coerce")
                avg_bw = parse_float(row["Avg BW"])
                total_bw = parse_float(row["Total BW"])
                code = extract_code(url)
                feature = extract_feature(url)
                title = extract_title(url)
                created_at = extract_created_at(url)
                consumed_at = "2023"
                imported_at = datetime.now().isoformat()
                eq_full = math.floor(full + 0.5 * partial) if pd.notnull(full) and pd.notnull(partial) else None

                if not all([url, title, consumed_at, imported_at]):
                    skipped += 1
                    continue

                c.execute("""
                    SELECT 1 FROM podcasts WHERE url = ? AND sheet_name = ?
                """, (url, sheet))
                if c.fetchone():
                    duplicates += 1
                    dup_rows.append((url, sheet))
                    continue

                c.execute("""
                    INSERT INTO podcasts (
                        url, title, code, feature, full, partial, avg_bw,
                        total_bw, eq_full, created_at, consumed_at,
                        imported_at, sheet_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, title, code, feature, full, partial, avg_bw, total_bw,
                    eq_full, str(created_at) if created_at else None,
                    consumed_at, imported_at, sheet
                ))
                inserted += 1
            except Exception:
                skipped += 1

    conn.commit()
    conn.close()

    pd.DataFrame(dup_rows, columns=["url", "sheet"]).to_csv("logs/duplicate_rows.csv", index=False)
    if dry_run:
        print(f"🔍 Would import {inserted} new rows (dry-run mode)")
    else:
        print(f"✅ Imported {inserted} new rows")
    print(f"🗂️  Duplicates logged: {duplicates}")
    print(f"🚫 Skipped rows: {skipped}")

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write to DB")
    parser.add_argument("path", help="Path to Excel file")
    parser.add_argument("--override-db", action="store_true", help="Override existing DB")
    args = parser.parse_args()
    import_from_excel(args.path, args.override_db, args.dry_run)
