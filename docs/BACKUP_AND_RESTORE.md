# Backup & Restore System: Streamlit + SQLite + Google Cloud Storage

## Overview
This project uses a robust, environment-aware backup and restore system for a Streamlit app with a SQLite database. Backups are stored in Google Cloud Storage (GCS) and can be managed both locally and in Google Cloud Run.

---

## Architecture Diagram

```
+-------------------+         +-------------------+         +-------------------+
|                   |         |                   |         |                   |
|   Streamlit App   +-------->+  BackupManager    +-------->+  Bash Scripts     |
|   (Home.py)       |         |  (Python)         |         |  (backup/restore) |
+-------------------+         +-------------------+         +-------------------+
                                                                |
                                                                v
                                                        +-------------------+
                                                        |                   |
                                                        |      gsutil       |
                                                        |                   |
                                                        +-------------------+
                                                                |
                                                                v
                                                        +-------------------+
                                                        |                   |
                                                        |      GCS          |
                                                        | (Backups Bucket)  |
                                                        +-------------------+
```

---

## How It Works

- **Backups** are created by Bash scripts (`scripts/backup-data.sh`) that compress the data directory and upload to GCS using `gsutil`.
- **Restores** are handled by Bash scripts (`scripts/startup-restore.sh`) that download the latest backup from GCS and extract it.
- **BackupManager** (Python) triggers these scripts, handles logging, and can schedule regular backups.
- **Streamlit Admin UI** allows manual backup/restore and viewing backup logs.

---

## Environment Handling

| Environment   | Data Path      | Script Path                | GCS Auth Method                | Service Account JSON Needed? |
|---------------|---------------|----------------------------|-------------------------------|------------------------------|
| Local         | `data/`       | `scripts/backup-data.sh`   | `GOOGLE_APPLICATION_CREDENTIALS` | **Yes** (for local dev)      |
| Cloud Run     | `/app/data`   | `/app/scripts/backup-data.sh` | Cloud Run Service Account      | No                           |

- **Paths** are auto-detected in scripts and Python code.
- **Python version for gsutil** is always set to 3.11 for compatibility.

---

## Authentication: Service Account JSON

- **Locally:**
  1. Copy the sample credentials file:
     ```bash
     cp config/gcs_credentials.json.sample config/gcs_credentials.json
     ```
  2. Edit `config/gcs_credentials.json` with your Google Cloud service account credentials
  3. This is used for all GCS operations by setting `GOOGLE_APPLICATION_CREDENTIALS`
- **Cloud Run:**
  - The app uses the service account attached to the Cloud Run service.
  - No JSON file is needed in the container.
  - Service account must have Storage Admin permissions.

---

## Required Environment Variables

- `GOOGLE_CLOUD_PROJECT`: Your Google Cloud project ID
- `BACKUP_BUCKET_NAME`: The name of your GCS bucket for backups
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account JSON (local only)

---

## Local Development Checklist

1. **Ensure you have Python 3.11 installed.**
2. **Set up credentials:**
   ```bash
   cp config/gcs_credentials.json.sample config/gcs_credentials.json
   # Edit config/gcs_credentials.json with your credentials
   ```
3. **Set environment variables:**
   ```bash
   export GOOGLE_CLOUD_PROJECT=your-project-id
   export BACKUP_BUCKET_NAME=your-backup-bucket
   export GOOGLE_APPLICATION_CREDENTIALS=config/gcs_credentials.json
   ```
4. **Run the app:**
   ```bash
   streamlit run app/Home.py
   ```
5. **Backups/Restores:**
   - Trigger from the Admin UI, or run scripts directly.
   - All GCS operations will use your service account key.

---

## Cloud Run Deployment Checklist

1. **Build and deploy your Docker image as described in `DEPLOY_TO_CLOUD_RUN.md`.**
2. **Attach a service account with GCS permissions to your Cloud Run service.**
3. **Set environment variables in Cloud Run:**
   - `GOOGLE_CLOUD_PROJECT`
   - `BACKUP_BUCKET_NAME`
4. **No need to include the JSON key in your Docker image.**
5. **Backups/Restores:**
   - Work the same way as locally, but use the Cloud Run service account for authentication.

---

## Troubleshooting

- **Password prompt or auth errors?**
  - Make sure `GOOGLE_APPLICATION_CREDENTIALS` is set and points to a valid service account key (locally).
  - Make sure the service account has the right GCS permissions.
  - Check that the service account has Storage Admin role.
- **Python version error with gsutil?**
  - Always set `CLOUDSDK_PYTHON=python3.11` for gsutil commands.
- **No objects found in GCS?**
  - Run a backup first; the folder will be empty until you do.
- **Permission denied errors?**
  - Verify service account permissions in Google Cloud Console.
  - Check that the bucket exists and is accessible.
  - Ensure the service account has Storage Admin role.

---

## FAQ

- **Do I need the JSON file in production?**
  - **No.** Only for local development/testing. Cloud Run uses its attached service account.
- **Can I use the Python GCS client?**
  - Yes, but all backup/restore operations here use `gsutil` for simplicity and reliability.
- **How often should I run backups?**
  - Daily backups are recommended for production environments.
  - Manual backups are sufficient for development.
- **Where are backup logs stored?**
  - Backup logs are stored in the `logs/` directory.
  - They are also visible in the Streamlit Admin UI.

---

For more details, see:
- `app/backup_manager.py` for the Python implementation
- `scripts/backup-data.sh` and `scripts/startup-restore.sh` for the shell scripts
- `DEPLOY_TO_CLOUD_RUN.md` for deployment instructions 