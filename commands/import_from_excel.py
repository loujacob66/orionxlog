import pandas as pd
import sqlite3
import os
import re
import math
from datetime import datetime
from argparse import ArgumentParser

def extract_code_feature_title(filename):
    from urllib.parse import unquote
    filename = unquote(filename).replace('.mp3', '').replace('.MP3', '')

    if match := re.match(r'^(\d{3})@(HPCpodcast|HPCNB|Mktg_Podcast)', filename):
        return match.group(1), match.group(2), filename[match.end() + 1:]

    if match := re.match(r'^(A\d{3})-', filename):
        return match.group(1), None, filename[match.end():]

    if match := re.match(r'^([A-Z]+)(\d{3})_', filename):
        return match.group(1) + match.group(2), match.group(1), filename[match.end():]

    if match := re.match(r'^(HPCpodcast|HPCNB|Mktg_Podcast|OXD)_', filename):
        return None, match.group(1), filename[match.end():]

    return None, None, filename

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
        print("🗑️ Existing database removed due to --override-db")

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
    seen_keys = set()

    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        df.columns = [col.strip() for col in df.columns]
        df["sheet_name"] = sheet

        if not {"URL", "Full", "Partial", "Avg BW", "Total BW"}.issubset(df.columns):
            continue

        df = df[df["URL"].astype(str).str.contains("/wp-content/uploads", na=False)].copy()

        for _, row in df.iterrows():
            try:
                url = row["URL"]
                sheet_name = row["sheet_name"]
                key = f"{url}::{sheet_name}"
                if key in seen_keys:
                    duplicates += 1
                    dup_rows.append((url, sheet_name))
                    continue
                seen_keys.add(key)

                full = pd.to_numeric(row["Full"], errors="coerce")
                partial = pd.to_numeric(row["Partial"], errors="coerce")
                avg_bw = parse_float(row["Avg BW"])
                total_bw = parse_float(row["Total BW"])
                code, feature, title = extract_code_feature_title(url.split("/")[-1])
                created_at = extract_created_at(url)
                consumed_at = f"{sheet_name}-01-01"
                imported_at = datetime.now().isoformat()
                eq_full = math.floor(full + 0.5 * partial) if pd.notnull(full) and pd.notnull(partial) else None

                if not all([url, title, consumed_at, imported_at]):
                    skipped += 1
                    continue

                if not dry_run:
                    c.execute("""
                        INSERT INTO podcasts (
                            url, title, code, feature, full, partial, avg_bw,
                            total_bw, eq_full, created_at, consumed_at,
                            imported_at, sheet_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        url, title, code, feature, full, partial, avg_bw, total_bw,
                        eq_full, str(created_at) if created_at else None,
                        consumed_at, imported_at, sheet_name
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
    print(f"🗂️ Duplicates logged: {duplicates}")
    print(f"🚫 Skipped rows: {4583 - (inserted + duplicates)}")

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("path", help="Path to Excel file")
    parser.add_argument("--override-db", action="store_true", help="Override existing DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write to DB")
    args = parser.parse_args()
    import_from_excel(args.path, args.override_db, args.dry_run)