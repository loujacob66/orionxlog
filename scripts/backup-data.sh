#!/bin/bash
set -e

# Configuration
BUCKET="${BUCKET_NAME:-orionxlog-backups}"
ENVIRONMENT="${ENVIRONMENT:-cloud}"
TIMESTAMP=$(date -u +"%Y-%m-%d_%H-%M-%S_UTC")

# Determine environment
if [ -d "/app/data" ] && [ -d "/app/config" ]; then
    DB_PATH="/app/data/podcasts.db"
    CONFIG_DIR="/app/config"
    BACKUP_DIR="/app/data/backups"
    ENVIRONMENT="cloud"
    echo "Running in Cloud Run environment"
else
    DB_PATH="$(pwd)/data/podcasts.db"
    CONFIG_DIR="$(pwd)/config"
    BACKUP_DIR="$(pwd)/data/backups"
    ENVIRONMENT="local"
    echo "Running in local development environment"
fi

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Verify GCS access
if ! gsutil ls "gs://${BUCKET}" > /dev/null 2>&1; then
    echo "Error: Failed to access GCS bucket"
    exit 1
fi

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database file not found at $DB_PATH"
    exit 1
fi

# Check if config exists
if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
    echo "Error: Config file not found at ${CONFIG_DIR}/config.yaml"
    exit 1
fi

# Count rows in the database
DB_ROW_COUNT="0" # Default to 0 if sqlite3 is not available or table doesn't exist
if command -v sqlite3 &> /dev/null && [ -f "$DB_PATH" ]; then
    DB_ROW_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM podcasts;" 2>/dev/null || echo "0")
    # If sqlite3 failed (e.g. table not found), it might output an error to stderr and non-zero exit.
    # The '|| echo "0"' ensures DB_ROW_COUNT is set to "0" in such cases.
    # A more robust check might be needed if 'podcasts' table might not exist yet.
    # For now, assume if db file exists, table should too, or count is 0.
    if ! [[ "$DB_ROW_COUNT" =~ ^[0-9]+$ ]]; then # Ensure it's a number
        echo "Warning: Failed to get valid row count from database. Defaulting to 0."
        DB_ROW_COUNT="0"
    fi
else
    echo "Warning: sqlite3 command not found or DB path incorrect. Row count will be 0."
fi
echo "Database row count: $DB_ROW_COUNT"

# Create backup archive filename including row count
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}_${ENVIRONMENT}_rows-${DB_ROW_COUNT}.tar.gz"
echo "Creating backup archive: $BACKUP_FILE"

# Create temporary directory for backup
TEMP_DIR=$(mktemp -d)
mkdir -p "${TEMP_DIR}/data" "${TEMP_DIR}/config"

# Copy files to temporary directory
cp "$DB_PATH" "${TEMP_DIR}/data/podcasts.db"
cp "${CONFIG_DIR}/config.yaml" "${TEMP_DIR}/config/config.yaml"

# Create archive
tar -czf "$BACKUP_FILE" -C "$TEMP_DIR" .

# Clean up temporary directory
rm -rf "$TEMP_DIR"

# Upload to GCS
echo "Uploading backup to GCS..."
if ! gsutil cp "$BACKUP_FILE" "gs://${BUCKET}/backups/$(basename "$BACKUP_FILE")"; then
    echo "Error: Failed to upload backup to GCS"
    exit 1
fi

# Clean up local backup file
rm "$BACKUP_FILE"

echo "Backup completed successfully" 