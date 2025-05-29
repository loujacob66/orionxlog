import subprocess
import threading
import time
import logging
from pathlib import Path
import os
# import streamlit as st # Not strictly needed for backend logic, consider removing if not used
from datetime import datetime, timezone # Added timezone
import sqlite3 # Added
import tarfile # Added

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, db_filename="podcasts.db", podcasts_table_name="podcasts", config_filename="config.yaml"): # Added params
        self.scheduler_thread = None
        self.stop_scheduler = threading.Event()
        self.scheduler_running = False
        
        self.db_filename = db_filename
        self.podcasts_table_name = podcasts_table_name
        self.config_filename = config_filename
        
        # Determine environment and base paths
        if os.path.exists("/app/data"):  # Cloud environment
            self.data_dir = "/app/data"
            self.config_dir = "/app/config" # Standard config location in cloud
            self.env_prefix = "cloud"
            logger.info("BackupManager initialized for Cloud environment.")
        else:  # Local environment
            project_root = Path(__file__).resolve().parent.parent # app -> project_root
            self.data_dir = str(project_root / "data")
            self.config_dir = str(project_root / "config")
            self.env_prefix = "local"
            logger.info(f"BackupManager initialized for Local environment. Data dir: {self.data_dir}, Config dir: {self.config_dir}")
            
        self.db_path = os.path.join(self.data_dir, self.db_filename)
        self.config_path = os.path.join(self.config_dir, self.config_filename)
        
        # Define staging dir path but do not create it here
        self.local_backups_staging_dir = os.path.join(self.data_dir, "backups_staging")

        self.gcs_backup_bucket_path = "gs://orionxlog-backups/backups/"
        logger.info(f"DB path set to: {self.db_path}")
        logger.info(f"Config path set to: {self.config_path}")
        logger.info(f"Local backup staging directory will be: {self.local_backups_staging_dir}")

    def _get_current_db_row_count(self):
        """Gets the row count of the primary table in the SQLite database."""
        if not os.path.exists(self.db_path):
            logger.warning(f"Database file not found at {self.db_path} for row count.")
            return None
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*) FROM "{self.podcasts_table_name}";') # Ensure table name is quoted
            count = cur.fetchone()[0]
            conn.close()
            logger.info(f"Successfully retrieved row count ({count}) from {self.db_path} for table {self.podcasts_table_name}")
            return count
        except sqlite3.Error as e:
            logger.error(f"SQLite error reading {self.db_path} for row count from table {self.podcasts_table_name}: {e}")
            return None

    def _generate_backup_filename_and_timestamp(self):
        """Generates the backup filename including environment and optional row count."""
        timestamp_utc = datetime.now(timezone.utc)
        timestamp_str = timestamp_utc.strftime("%Y-%m-%d_%H-%M-%S")
        
        row_count = self._get_current_db_row_count()
        
        if row_count is not None:
            filename = f"backup_{timestamp_str}_UTC_{self.env_prefix}_rows-{row_count}.tar.gz"
        else:
            filename = f"backup_{timestamp_str}_UTC_{self.env_prefix}_rows-NA.tar.gz"
            logger.warning(f"Could not determine row count. Backup filename will be: {filename}")
            
        return filename, timestamp_utc

    def run_backup(self):
        """Creates a backup of DB and config, names it with row count, and uploads to GCS."""
        logger.info("Starting backup process...")

        # Ensure the local staging directory exists
        try:
            os.makedirs(self.local_backups_staging_dir, exist_ok=True)
            logger.info(f"Ensured staging directory exists: {self.local_backups_staging_dir}")
        except OSError as e:
            logger.error(f"CRITICAL: Failed to create staging directory {self.local_backups_staging_dir} in run_backup: {e}")
            return False # Cannot proceed without staging directory

        backup_filename, _ = self._generate_backup_filename_and_timestamp()
        local_tar_path = os.path.join(self.local_backups_staging_dir, backup_filename)

        files_to_archive = []
        if os.path.exists(self.db_path):
            files_to_archive.append({'path': self.db_path, 'arcname': self.db_filename})
            logger.info(f"Database file {self.db_path} found and will be added to backup.")
        else:
            logger.warning(f"Database file {self.db_path} not found. Skipping from backup.")

        if os.path.exists(self.config_path):
            files_to_archive.append({'path': self.config_path, 'arcname': self.config_filename})
            logger.info(f"Config file {self.config_path} found and will be added to backup.")
        else:
            logger.warning(f"Config file {self.config_path} not found. Skipping from backup.")

        if not files_to_archive:
            logger.error("No files (database or config) found to backup. Aborting backup.")
            return False

        try:
            with tarfile.open(local_tar_path, "w:gz") as tar:
                for item in files_to_archive:
                    tar.add(item['path'], arcname=item['arcname'])
            logger.info(f"Successfully created local backup archive: {local_tar_path}")
        except Exception as e:
            logger.error(f"Failed to create local tar archive {local_tar_path}: {e}")
            if os.path.exists(local_tar_path):
                try: os.remove(local_tar_path)
                except OSError as oe: logger.error(f"Error removing partial archive {local_tar_path}: {oe}")
            return False
        
        gcs_destination_path = f"{self.gcs_backup_bucket_path.rstrip('/')}/{backup_filename}"
        try:
            env = os.environ.copy()
            env["CLOUDSDK_PYTHON"] = "python3.11" 
            logger.info(f"Uploading {local_tar_path} to {gcs_destination_path}...")
            result = subprocess.run(
                ["gsutil", "cp", local_tar_path, gcs_destination_path],
                capture_output=True, text=True, check=True, env=env
            )
            logger.info(f"Backup uploaded successfully to GCS: {gcs_destination_path}")
            logger.debug(f"gsutil output: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Backup upload to GCS failed. gsutil stderr: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during GCS upload: {str(e)}")
            return False
        finally:
            if os.path.exists(local_tar_path):
                try:
                    os.remove(local_tar_path)
                    logger.info(f"Cleaned up local backup archive: {local_tar_path}")
                except OSError as e:
                    logger.error(f"Error cleaning up local archive {local_tar_path}: {e}")

    def start_backup_scheduler(self):
        """Start the background backup scheduler only if not already running."""
        if not self.scheduler_running:
            def backup_loop():
                self.scheduler_running = True
                logger.info("Backup scheduler loop started. Initial delay before first backup.")
                # Wait for 5 minutes before running the first backup
                time.sleep(300) # 5 minutes
                
                while not self.stop_scheduler.is_set():
                    logger.info("Scheduler invoking run_backup().")
                    try:
                        success = self.run_backup()
                        if success:
                            logger.info("Scheduled backup completed successfully.")
                        else:
                            logger.warning("Scheduled backup failed.")
                    except Exception as e:
                        logger.error(f"Exception in backup scheduler loop: {str(e)}", exc_info=True)
                    
                    # Sleep for 1 hour (3600 seconds)
                    # Check stop_scheduler event periodically during sleep to allow faster shutdown
                    for _ in range(360): # Check every 10 seconds for 1 hour
                        if self.stop_scheduler.is_set():
                            break
                        time.sleep(10)
                    if self.stop_scheduler.is_set():
                        logger.info("Stop event set, exiting backup_loop.")
                        break
            
            self.scheduler_thread = threading.Thread(target=backup_loop, daemon=True)
            self.scheduler_thread.start()
            logger.info("Backup scheduler thread started.")
        else:
            logger.info("Backup scheduler already running.")
    
    def stop_backup_scheduler(self):
        """Stop the backup scheduler."""
        if self.scheduler_running and self.scheduler_thread is not None:
            logger.info("Stopping backup scheduler...")
            self.stop_scheduler.set()
            self.scheduler_thread.join(timeout=15) # Increased timeout slightly
            if self.scheduler_thread.is_alive():
                logger.warning("Backup scheduler thread did not terminate in time.")
            self.scheduler_running = False
            self.stop_scheduler.clear() # Reset event for potential restart
            logger.info("Backup scheduler stopped.")
        else:
            logger.info("Backup scheduler not running or thread not found.") 