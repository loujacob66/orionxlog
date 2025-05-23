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

# Create backup archive
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}_${ENVIRONMENT}.tar.gz"
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