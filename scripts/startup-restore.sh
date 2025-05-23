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
while IFS= read -r backup; do
    filename=$(basename "$backup")
    if [[ $filename =~ backup_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{2}-[0-9]{2}-[0-9]{2})_UTC_([^.]+)\.tar\.gz ]] || 
       [[ $filename =~ backup_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{2}-[0-9]{2}-[0-9]{2})_([^.]+)_[0-9]+K_unknownrows\.tar\.gz ]]; then
        date_str="${BASH_REMATCH[1]}"
        time_str="${BASH_REMATCH[2]}"
        env="${BASH_REMATCH[3]}"
        
        # Only consider backups from the same environment
        if [ "$env" = "$ENVIRONMENT" ]; then
            timestamp="${date_str} ${time_str}"
            if [ -z "$LATEST_TIMESTAMP" ] || [ "$timestamp" \> "$LATEST_TIMESTAMP" ]; then
                LATEST_TIMESTAMP="$timestamp"
                LATEST_BACKUP="$backup"
            fi
        fi
    fi
done <<< "$BACKUPS"

if [ -z "$LATEST_BACKUP" ]; then
    echo "No backups found for environment: $ENVIRONMENT"
    exit 0
fi

echo "Found backup: $LATEST_BACKUP"

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
else
    echo "Error: config.yaml not found in backup"
    exit 1
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