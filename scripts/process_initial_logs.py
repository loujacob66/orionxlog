#!/usr/bin/env python3
import os
import sys
import argparse
from datetime import datetime
from import_data import import_data

def process_initial_logs(override=False, dry_run=False, reset_db=False):
    """
    Process all Excel files in the data/initial_logs directory.
    Monthly files are processed first, followed by the report file.
    
    Args:
        override: Whether to override existing data
        dry_run: Whether to perform a dry run
        reset_db: Whether to reset the database before import
    """
    initial_logs_dir = os.path.join("data", "initial_logs")
    
    if not os.path.exists(initial_logs_dir):
        print(f"Error: Initial logs directory not found at {initial_logs_dir}")
        return False
    
    # Get all files from initial_logs directory
    initial_files = []
    for file in os.listdir(initial_logs_dir):
        if file.endswith(('.xlsx', '.xls')):
            file_path = os.path.join(initial_logs_dir, file)
            initial_files.append(file_path)
    
    if not initial_files:
        print("Warning: No Excel files found in initial_logs directory")
        return False

    # Sort files to ensure monthly data is processed before report
    monthly_files = [f for f in initial_files if not f.endswith('report0416.xls')]
    report_file = [f for f in initial_files if f.endswith('report0416.xls')]
    
    total_stats = {
        'sheets': {'processed': 0, 'total': 0},
        'rows': {'scanned': 0, 'merged': 0, 'errors': 0},
        'actual': {'inserted': 0, 'replaced': 0, 'ignored': 0}
    }
    
    # Process monthly files first
    if monthly_files:
        print("\nProcessing Monthly Files:")
        print("=" * 50)
        for file_path in monthly_files:
            print(f"\nProcessing {os.path.basename(file_path)}...")
            stats = import_data(
                filepath=file_path,
                override=override,
                dry_run=dry_run,
                reset_db=reset_db if file_path == monthly_files[0] else False
            )
            if stats:
                accumulate_stats(total_stats, stats)
                display_import_summary(stats, override, reset_db, dry_run)
    
    # Process report file last
    if report_file:
        print("\nProcessing Report File:")
        print("=" * 50)
        for file_path in report_file:
            print(f"\nProcessing {os.path.basename(file_path)}...")
            stats = import_data(
                filepath=file_path,
                override=override,
                dry_run=dry_run,
                reset_db=False  # Never reset DB for report file
            )
            if stats:
                accumulate_stats(total_stats, stats)
                display_import_summary(stats, override, reset_db, dry_run)
    
    # Display total summary
    print("\nTotal Import Summary:")
    print("=" * 50)
    display_import_summary(total_stats, override, reset_db, dry_run)
    
    return True

def accumulate_stats(total_stats, stats):
    """Accumulate statistics from individual imports"""
    total_stats['sheets']['processed'] += stats['sheets']['processed']
    total_stats['sheets']['total'] += stats['sheets']['total']
    total_stats['rows']['scanned'] += stats['rows']['scanned']
    total_stats['rows']['merged'] += stats['rows']['merged']
    total_stats['rows']['errors'] += stats['rows']['errors']
    total_stats['actual']['inserted'] += stats['actual']['inserted']
    total_stats['actual']['replaced'] += stats['actual']['replaced']
    total_stats['actual']['ignored'] += stats['actual']['ignored']

def display_import_summary(stats, override, reset_db, dry_run):
    """Display a summary of the import process"""
    print(f"\nAction Taken: {get_import_action_summary(override, reset_db, dry_run)}")
    print(f"Total sheets processed: {stats['sheets']['processed']} / {stats['sheets']['total']}")
    print(f"Total rows scanned: {stats['rows']['scanned']}")
    print(f"Total rows merged: {stats['rows']['merged']}")
    print(f"Total rows with errors: {stats['rows']['errors']}")
    print(f"Dry run: {dry_run}")
    print(f"Total inserted: {stats['actual']['inserted']}")
    print(f"Total replaced: {stats['actual']['replaced']}")
    print(f"Total ignored: {stats['actual']['ignored']}")

def get_import_action_summary(override, reset_db, dry_run):
    """Get a summary of what actions will be taken"""
    if dry_run:
        if reset_db:
            return "This was a dry run. No changes were made to the database.\nIf this were not a dry run: The entire database would be deleted before import. Only data from this file would remain after import."
        elif override:
            return "This was a dry run. No changes were made to the database.\nIf this were not a dry run: Rows for the same period (month/year) would be overwritten. All other data would remain unchanged."
        else:
            return "This was a dry run. No changes were made to the database.\nIf this were not a dry run: New rows would be added. Existing rows for the same period would be ignored (not overwritten). All other data would remain unchanged."
    else:
        if reset_db:
            return "The entire database was deleted before import. Only data from this file remains after import."
        elif override:
            return "Rows for the same period (month/year) were overwritten. All other data remains unchanged."
        else:
            return "New rows were added. Existing rows for the same period were ignored (not overwritten). All other data remains unchanged."

def main():
    parser = argparse.ArgumentParser(description='Process initial logs from data/initial_logs directory')
    parser.add_argument('--override', action='store_true', help='Update existing data for the same month/year')
    parser.add_argument('--reset-db', action='store_true', help='Clear all existing data before import')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
    
    args = parser.parse_args()
    
    print(f"Starting import process at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Options: override={args.override}, reset_db={args.reset_db}, dry_run={args.dry_run}")
    
    success = process_initial_logs(
        override=args.override,
        dry_run=args.dry_run,
        reset_db=args.reset_db
    )
    
    if success:
        print("\nImport process completed successfully!")
    else:
        print("\nImport process failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 