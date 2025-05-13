import sys
import argparse
from scripts.import_data import import_data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filepath", help="Path to the data file (Excel)")
    parser.add_argument("--override-db", action="store_true", help="Override the existing database")
    parser.add_argument("--dry-run", action="store_true", help="Run without making any changes")
    args = parser.parse_args()

    import_data(args.filepath, override=args.override_db, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
