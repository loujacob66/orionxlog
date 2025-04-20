import sys
import argparse
from commands.import_from_excel import import_excel

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("excel_path", help="Path to the Excel file")
    parser.add_argument("--override-db", action="store_true", help="Override the existing database")
    parser.add_argument("--dry-run", action="store_true", help="Run without making any changes")
    args = parser.parse_args()

    import_excel(args.excel_path, override=args.override_db, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
