#!/bin/bash
set -e

# Configuration
BUCKET="${BUCKET_NAME:-orionxlog-backups}"
TEMP_DIR="/tmp/orionxlog_restore"

# Cleanup function
cleanup() {
    rm -rf "$TEMP_DIR"
}

# Ensure clean state
trap cleanup EXIT
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Determine environment
if [ -d "/app/data" ] && [ -d "/app/config" ]; then
    RESTORE_DIR="/app/data"
    CONFIG_DIR="/app/config"
    ENVIRONMENT="${ENVIRONMENT:-cloud}"
    echo "Running in Cloud Run environment"
else
    RESTORE_DIR="$(pwd)/data"
    CONFIG_DIR="$(pwd)/config"
    ENVIRONMENT="local"
    echo "Running in local development environment"
fi

# Create directories if they don't exist
mkdir -p "$RESTORE_DIR" "$CONFIG_DIR"

# Verify GCS access
if ! gsutil ls "gs://${BUCKET}" > /dev/null 2>&1; then
    echo "Error: Failed to access GCS bucket"
    exit 1
fi

# Get latest backup
echo "Finding latest backup..."
BACKUPS=$(gsutil ls "gs://${BUCKET}/backups/")
LATEST_BACKUP=""
LATEST_TIMESTAMP=""

# Parse and sort backups by timestamp
echo "Available backups:"
while IFS= read -r backup; do
    filename=$(basename "$backup")
    if [[ $filename =~ backup_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{2}-[0-9]{2}-[0-9]{2})_UTC_([^.]+)\.tar\.gz ]] || 
       [[ $filename =~ backup_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{2}-[0-9]{2}-[0-9]{2})_([^.]+)_[0-9]+K_unknownrows\.tar\.gz ]]; then
        date_str="${BASH_REMATCH[1]}"
        time_str="${BASH_REMATCH[2]}"
        env="${BASH_REMATCH[3]}"
        
        # Convert UTC to local time using Python
        utc_timestamp="${date_str} ${time_str}"
        local_timestamp=$(python3 -c "
from datetime import datetime
import pytz
utc_time = datetime.strptime('${utc_timestamp}', '%Y-%m-%d %H-%M-%S')
utc_time = pytz.UTC.localize(utc_time)
local_time = utc_time.astimezone()
print(local_time.strftime('%Y-%m-%d %H:%M:%S %Z'))
")
        
        # Consider all backups and let timestamp comparison handle it
        timestamp="${date_str} ${time_str}"
        echo "Found backup: $filename (${utc_timestamp} UTC -> ${local_timestamp}, $env environment)"
        if [ -z "$LATEST_TIMESTAMP" ] || [ "$timestamp" \> "$LATEST_TIMESTAMP" ]; then
            LATEST_TIMESTAMP="$timestamp"
            LATEST_BACKUP="$backup"
            echo "  -> New latest backup selected"
        fi
    fi
done <<< "$BACKUPS"

if [ -z "$LATEST_BACKUP" ]; then
    echo "No backups found for environment: $ENVIRONMENT"
    echo "Creating initial database..."
    echo "No backup found - creating fresh database" > /tmp/restore_status.txt
    
    # Create initial database using Python
    python3 -c "
import sqlite3
import os

# Create database directory if it doesn't exist
os.makedirs('$RESTORE_DIR', exist_ok=True)

# Connect to database (this will create it if it doesn't exist)
conn = sqlite3.connect('$RESTORE_DIR/podcasts.db')
cursor = conn.cursor()

# Create necessary tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS podcasts (
    url TEXT NOT NULL,
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
    consumed_year INTEGER NOT NULL, 
    consumed_month INTEGER NOT NULL,
    assumed_month INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT,
    source_file_path TEXT,
    PRIMARY KEY (url, consumed_year, consumed_month)
)
''')

# Commit changes and close connection
conn.commit()
conn.close()
"
    
    # Set proper permissions
    chmod 600 "$RESTORE_DIR/podcasts.db"
    chmod 700 "$RESTORE_DIR"
    
    echo "Initial database created successfully"
    exit 0
fi

echo "Found backup: $LATEST_BACKUP"

# Extract date and time from backup filename
filename=$(basename "$LATEST_BACKUP")
if [[ $filename =~ backup_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{2}-[0-9]{2}-[0-9]{2})_UTC_([^.]+)\.tar\.gz ]]; then
    BACKUP_DATE="${BASH_REMATCH[1]}"
    BACKUP_TIME="${BASH_REMATCH[2]}"
    BACKUP_ENV="${BASH_REMATCH[3]}"
    utc_timestamp="${BACKUP_DATE} ${BACKUP_TIME}"
    # Convert UTC to local time using Python
    local_timestamp=$(python3 -c "
from datetime import datetime
import pytz
utc_time = datetime.strptime('${utc_timestamp}', '%Y-%m-%d %H-%M-%S')
utc_time = pytz.UTC.localize(utc_time)
local_time = utc_time.astimezone()
print(local_time.strftime('%Y-%m-%d %H:%M:%S %Z'))
")
    echo "Restoring from backup dated ${utc_timestamp} UTC (${local_timestamp}, ${BACKUP_ENV} environment)" > /tmp/restore_status.txt
else
    echo "Restoring from backup: $filename" > /tmp/restore_status.txt
fi

# Download backup
echo "Downloading backup..."
if ! gsutil cp "$LATEST_BACKUP" "${TEMP_DIR}/backup.tar.gz"; then
    echo "Error: Failed to download backup"
    exit 1
fi

# Extract backup
echo "Extracting backup..."
if ! tar -xzf "${TEMP_DIR}/backup.tar.gz" -C "$TEMP_DIR"; then
    echo "Error: Failed to extract backup"
    exit 1
fi

# Restore config
if [ -f "${TEMP_DIR}/config/config.yaml" ]; then
    echo "Restoring config..."
    cp "${TEMP_DIR}/config/config.yaml" "${CONFIG_DIR}/config.yaml"
    chmod 600 "${CONFIG_DIR}/config.yaml"
fi

# Restore database
if [ -f "${TEMP_DIR}/data/podcasts.db" ]; then
    echo "Restoring database..."
    cp "${TEMP_DIR}/data/podcasts.db" "${RESTORE_DIR}/podcasts.db"
    chmod 600 "${RESTORE_DIR}/podcasts.db"
else
    echo "Error: Database not found in backup"
    exit 1
fi

# Set directory permissions
chmod 700 "$RESTORE_DIR" "$CONFIG_DIR"

echo "Restore completed successfully" 