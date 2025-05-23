import subprocess
import threading
import time
import logging
from pathlib import Path
import os
import streamlit as st
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self):
        self.scheduler_thread = None
        self.stop_scheduler = threading.Event()
        self.scheduler_running = False
        
    def run_backup(self):
        """Run the backup script"""
        try:
            logger.info("Starting backup process...")
            # Create a copy of the current environment
            env = os.environ.copy()
            
            # Ensure Python version is set for gsutil
            env["CLOUDSDK_PYTHON"] = "python3.11"
            
            # Run the backup script with the environment
            result = subprocess.run(
                ["bash", "scripts/backup-data.sh"],
                capture_output=True,
                text=True,
                check=True,
                env=env  # Pass the environment to the subprocess
            )
            logger.info("Backup completed successfully")
            logger.debug(f"Backup output: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = f"Backup failed: {e.stderr}"
            logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Unexpected error during backup: {str(e)}"
            logger.error(error_msg)
            return False

    def start_backup_scheduler(self):
        """Start the background backup scheduler only if not already running."""
        if not self.scheduler_running:
            def backup_loop():
                self.scheduler_running = True
                # Wait for 5 minutes before running the first backup
                # This prevents double execution when the scheduler starts
                time.sleep(300)
                
                while not self.stop_scheduler.is_set():
                    try:
                        self.run_backup()
                    except Exception as e:
                        logger.error(f"Error in backup scheduler: {str(e)}")
                    time.sleep(3600)  # Sleep for 1 hour
            
            self.scheduler_thread = threading.Thread(target=backup_loop, daemon=True)
            self.scheduler_thread.start()
            logger.info("Backup scheduler started")
    
    def stop_backup_scheduler(self):
        """Stop the backup scheduler."""
        if self.scheduler_running:
            self.stop_scheduler.set()
            if self.scheduler_thread:
                self.scheduler_thread.join(timeout=5)
            self.scheduler_running = False
            logger.info("Backup scheduler stopped") 