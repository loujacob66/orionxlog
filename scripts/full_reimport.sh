#!/bin/bash

# Script to clear the database and re-import all podcast log data.

# Exit immediately if a command exits with a non-zero status.
set -e

DB_PATH="data/podcasts.db"
LOGS_DIR="data/podcast_logs"
IMPORT_SCRIPT="scripts/import_data.py"

# --- Safety check for python script ---
if [ ! -f "$IMPORT_SCRIPT" ]; then
    echo "Error: Import script not found at $IMPORT_SCRIPT" >&2
    exit 1
fi

# --- Clear the database ---
echo "🗑️  Clearing the database: $DB_PATH ..."
rm -f "$DB_PATH"
echo "✅ Database cleared."

# --- Define the order of files ---
# Monthly files first, sorted chronologically
# Then specific report files

# Specific report file(s) to process last
report_file_main="$LOGS_DIR/report0416.xlsx"

# --- Process monthly files ---
echo "
🔄 Processing monthly log files..."
find "$LOGS_DIR" -maxdepth 1 -type f -name "[0-9][0-9][0-9][0-9][0-1][0-9][0-3][0-9]_podcast_downloads.xlsx" | sort | \
while IFS= read -r file_path; do
    if [ -f "$file_path" ]; then
        echo "
👉 Importing Monthly: $file_path ..."
        python "$IMPORT_SCRIPT" "$file_path"
    else
        # This condition might be unlikely if find just found it, but good practice
        echo "⚠️ Warning: Monthly file $file_path somehow not found during processing, skipping." >&2
    fi
done
echo "✅ Monthly log files processed."

# --- Process the main report file ---
echo "
🔄 Processing main report file..."
if [ -f "$report_file_main" ]; then
    echo "
👉 Importing $report_file_main ..."
    python "$IMPORT_SCRIPT" "$report_file_main"
    echo "✅ Main report file processed."
else
    echo "⚠️ Error: Main report file $report_file_main not found!" >&2
    # Decide if this should be a fatal error for your workflow
    # exit 1 
fi

echo "
🎉 All data re-imported successfully!"

# Make the script executable by default upon creation
# chmod +x scripts/full_reimport.sh
# You will likely need to run `chmod +x scripts/full_reimport.sh` once manually in your terminal. 