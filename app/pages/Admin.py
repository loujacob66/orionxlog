import streamlit as st
st.set_page_config(layout="wide", page_title="Admin Dashboard", page_icon="🔧")

# Add CSS to hide sidebar initially
st.markdown("""
    <style>
        section[data-testid="stSidebar"] {
            display: none;
        }
    </style>
""", unsafe_allow_html=True)

import os
import sys
import yaml
import io
from datetime import datetime, timezone, timedelta
import shutil
import subprocess
import pandas as pd
import time
import re
import tempfile
import hashlib
import contextlib
import streamlit_authenticator as stauth
import sqlite3 # Added for get_db_row_count

# Define directory paths
if os.path.exists("/app/data"):
    # Cloud environment
    data_dir = "/app/data" # Define data_dir for cloud
    backups_dir = os.path.join(data_dir, "backups")
    permanent_upload_dir = os.path.join(data_dir, "uploaded")
else:
    # Local environment
    data_dir = "data" # Define data_dir for local
    backups_dir = os.path.join(data_dir, "backups")
    permanent_upload_dir = os.path.join(data_dir, "uploaded")

database_file_path = os.path.join(data_dir, "podcasts.db")

# Create directories if they don't exist
os.makedirs(data_dir, exist_ok=True) # Ensure base data directory exists too
os.makedirs(backups_dir, exist_ok=True)
os.makedirs(permanent_upload_dir, exist_ok=True)

# GCS bucket configuration
BUCKET_NAME = "orionxlog-uploaded-files"
BUCKET_URL = f"gs://{BUCKET_NAME}"

def get_db_row_count(db_path, table_name="podcasts"):
    """Get the row count of a specific table in a SQLite database."""
    if not os.path.exists(db_path):
        return None # Or 0 or specific error indicator
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error as e:
        # st.warning(f"SQLite error reading {db_path} for row count: {e}") # Optional: log this
        return None # Indicate error or inability to read

def list_bucket_files():
    """List all files in the GCS bucket with their metadata, optimized."""
    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"
        # Get detailed list with size and timestamp
        result = subprocess.run(
            ["gsutil", "ls", "-l", f"{BUCKET_URL}/"],
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        lines = result.stdout.strip().split('\n')
        files = []
        for line in lines:
            if not line.strip() or line.strip().startswith('TOTAL:'):  # Skip empty lines and total line
                continue
            
            parts = line.strip().split(None, 2) # Split into max 3 parts: size, date, name
            if len(parts) < 3:
                st.warning(f"Skipping malformed line from gsutil ls -l: {line}")
                continue
            
            try:
                size_str, timestamp_str, gcs_url_part = parts
                size = int(size_str)
                gcs_url = gcs_url_part # This is the full gs:// path
                filename = os.path.basename(gcs_url)
                
                # Parse the UTC timestamp (e.g., "2023-07-14T00:05:02Z")
                update_time_utc = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                # Convert to local timezone for display
                display_date = update_time_utc.astimezone().strftime("%b %d, %Y %H:%M:%S %Z")
                
                files.append({
                    'name': filename,
                    'size': size,
                    'updated': update_time_utc, # Store UTC datetime object for sorting
                    'display_date': display_date,
                    'size_display': f"{size/1024/1024:.2f} MB",
                    'url': gcs_url
                })
            except ValueError as ve:
                st.warning(f"Skipping line due to parsing error ('{line}'): {ve}")
                continue
            except Exception as e: # Catch any other unexpected error during parsing a line
                st.warning(f"Skipping file entry due to unexpected error ('{line}'): {e}")
                continue
        
        # Sort by updated time (UTC), most recent first, then by name for stability
        files.sort(key=lambda x: x['name']) # Sort by name first (Python's sort is stable)
        files.sort(key=lambda x: x['updated'], reverse=True) # Then sort by updated time (most recent first)
        return files
    except subprocess.CalledProcessError as e:
        st.error(f"Error accessing GCS to list files: {e.stderr}")
        return []
    except Exception as e: # Catch broader errors like gsutil not found or network issues
        st.error(f"Unexpected error while listing GCS files: {str(e)}")
        return []

def upload_to_bucket(files_data_list, filenames_list):
    """Upload multiple files to the GCS bucket using a single gsutil -m cp command."""
    if not files_data_list or not filenames_list or len(files_data_list) != len(filenames_list):
        st.warning("upload_to_bucket: Mismatch or empty file lists provided.")
        return {"success": 0, "error": 0, "skipped": 0}

    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"

        with tempfile.TemporaryDirectory() as temp_dir_for_upload:
            local_files_to_upload_for_gsutil_cmd = []
            
            for file_data_item, filename_item in zip(files_data_list, filenames_list):
                local_filepath = os.path.join(temp_dir_for_upload, filename_item)
                try:
                    with open(local_filepath, 'wb') as f:
                        f.write(file_data_item.getvalue())
                    local_files_to_upload_for_gsutil_cmd.append(local_filepath)
                except Exception as e:
                    st.error(f"Failed to write temporary file {filename_item}: {e}")
                    # Decide how to count this error - perhaps add to a separate error list
                    # For now, this means it won't be part of the gsutil command.
            
            if not local_files_to_upload_for_gsutil_cmd:
                st.info("No files were prepared for upload after temporary writing.")
                return {"success": 0, "error": len(filenames_list), "skipped": 0} # All failed if none prepared

            # Command: gsutil -m cp /tmp/somedir/fileA.xlsx /tmp/somedir/fileB.xls ... gs://BUCKET_URL/
            cmd = ["gsutil", "-m", "cp"] + local_files_to_upload_for_gsutil_cmd + [f"{BUCKET_URL}/"]
            
            # st.write(f"Executing GCS Upload Command: {' '.join(cmd)}") # For debugging

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True, 
                env=env
            )
            # If check=True, CalledProcessError is raised on non-zero exit.
            # gsutil -m cp can have partial successes/failures.
            # A non-zero exit code usually means at least one file failed.
            # Parsing stderr for "Some files failed" is more robust for -m.
            
            # For simplicity here, if no exception, assume all specified local files were attempted.
            # A more advanced version would parse `result.stderr` for per-file errors if `check=False`.
            return {"success": len(local_files_to_upload_for_gsutil_cmd), "error": 0, "skipped": 0}

    except subprocess.CalledProcessError as e:
        st.error(f"Error during batch GCS upload (gsutil command failed): {e.stderr}")
        # It's hard to know exactly how many succeeded/failed from a general CalledProcessError with -m
        # without parsing stderr. Assume all attempted files in this batch failed for simplicity.
        return {"success": 0, "error": len(filenames_list), "skipped": 0}
    except Exception as e:
        st.error(f"Unexpected error during batch GCS upload preparation or execution: {str(e)}")
        return {"success": 0, "error": len(filenames_list), "skipped": 0}
    # TemporaryDirectory cleans itself up automatically.

def delete_from_bucket(filenames):
    """Delete multiple files from the GCS bucket using a single gsutil -m rm command."""
    if not filenames:
        return {"success": 0, "error": 0} # No files to delete

    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"
        
        # Construct full GCS paths for each filename
        gcs_paths_to_delete = [f"{BUCKET_URL}/{filename}" for filename in filenames]
        
        # Command: gsutil -m rm gs://bucket/file1 gs://bucket/file2 ...
        cmd = ["gsutil", "-m", "rm"] + gcs_paths_to_delete
        
        # st.write(f"Executing GCS Delete Command: {' '.join(cmd)}") # For debugging

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True, # Will raise CalledProcessError on failure
            env=env
        )
        # If check=True and no error, assume all specified files were deleted successfully by gsutil.
        # Similar to upload, robustly determining partial success/failure from `gsutil -m rm` output 
        # without `check=True` would require parsing stderr.
        return {"success": len(filenames), "error": 0}

    except subprocess.CalledProcessError as e:
        st.error(f"Error during batch GCS delete (gsutil command failed): {e.stderr}")
        # Assume all attempted files in this batch failed for simplicity if the command itself fails.
        return {"success": 0, "error": len(filenames)}
    except Exception as e:
        st.error(f"Unexpected error during batch GCS delete: {str(e)}")
        return {"success": 0, "error": len(filenames)}

def batch_download_from_bucket(gcs_filenames, local_temp_dir):
    """Download multiple files from GCS to a local temporary directory in parallel."""
    if not gcs_filenames:
        st.info("No GCS filenames provided for batch download.")
        return {}, [] # No files to download, no successes, no failures

    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = "python3.11"
    
    gcs_full_paths = [f"{BUCKET_URL}/{filename}" for filename in gcs_filenames]
    
    # Command: gsutil -m cp gs://bucket/file1 gs://bucket/file2 ... /local/temp/dir/
    cmd = ["gsutil", "-m", "cp"] + gcs_full_paths + [local_temp_dir]
    
    downloaded_files_map = {}
    failed_files = []

    try:
        # st.write(f"Executing GCS Batch Download Command: {' '.join(cmd)}") # For debugging
        # Using subprocess.run which waits for completion.
        # Real-time progress from gsutil -m is complex to capture and display in Streamlit
        # without streaming, so we'll show a general message.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False, # We will check stderr for failures, as -m can have partial success
            env=env
        )

        # After gsutil -m cp, successfully copied files will be in local_temp_dir.
        # We need to confirm which ones actually made it.
        for original_filename in gcs_filenames:
            local_path = os.path.join(local_temp_dir, original_filename)
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                downloaded_files_map[original_filename] = local_path
            else:
                # File wasn't found locally or is empty, assume it failed or was skipped by gsutil.
                failed_files.append(original_filename)
        
        # Check stderr for common gsutil -m error patterns if some files are missing
        if result.stderr:
            # gsutil -m cp is tricky: it can succeed for some files and fail for others,
            # and the overall exit code might still be 0 if at least one file succeeded,
            # or non-zero if any file failed.
            # A simple check is to see if stderr contains "Some files failed" or "Error".
            if "Some files failed" in result.stderr or "Error:" in result.stderr.lower() or result.returncode != 0:
                 # This indicates gsutil itself reported issues. Our file existence check above
                 # should catch most individual failures. This is a general warning.
                 st.warning(f"gsutil reported some issues during batch download.Stderr: {result.stderr[:500]}...") # Log snippet of stderr
            # If no specific error message and all files are present, we can assume success.
            # If some files are missing but gsutil didn't explicitly report "Some files failed", they might have been skipped for other reasons.

        if not downloaded_files_map and gcs_filenames: # No files downloaded, but some were expected
             st.error("Batch download command ran, but no files were successfully downloaded to the temporary directory.")
             failed_files = list(gcs_filenames) # Mark all as failed if none were found

        return downloaded_files_map, failed_files

    except subprocess.CalledProcessError as e: # Should not be hit if check=False, but good practice
        st.error(f"Critical error executing gsutil batch download (CalledProcessError): {e.stderr}")
        return {}, list(gcs_filenames) # All failed
    except FileNotFoundError: # gsutil not found
        st.error("gsutil command not found. Please ensure Google Cloud SDK is installed and in PATH.")
        return {}, list(gcs_filenames)
    except Exception as e:
        st.error(f"Unexpected error during GCS batch download: {str(e)}")
        return {}, list(gcs_filenames) # All failed

def download_from_bucket(filename):
    """Download a file from the GCS bucket to a temporary location."""
    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            subprocess.run(
                ["gsutil", "cp", f"{BUCKET_URL}/{filename}", temp_file.name],
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
            return temp_file.name
    except subprocess.CalledProcessError as e:
        st.error(f"Error downloading file: {e.stderr}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None

# Helper function to accumulate import statistics
def accumulate_stats(total_stats, new_stats):
    """Accumulate statistics from multiple import operations."""
    for category in total_stats:
        if category == 'unprocessed_sheets_details':
            # Assuming new_stats might contain a list of unprocessed sheet details for the current file
            # Each item in this list should ideally include the original filename
            if 'unprocessed_sheet_info' in new_stats and isinstance(new_stats['unprocessed_sheet_info'], list):
                for item in new_stats['unprocessed_sheet_info']:
                    detail = {
                        'original_filename': new_stats.get('filename', 'Unknown Source File'),
                        'sheet_name': item.get('sheet_name', 'Unknown Sheet'),
                        'reason': item.get('reason', 'No reason provided')
                    }
                    total_stats['unprocessed_sheets_details'].append(detail)
        elif category == 'filename': # Don't sum up filenames
            pass 
        else: # For 'sheets', 'rows', 'actual'
            for stat in total_stats[category]:
                if stat in new_stats.get(category, {}):
                    total_stats[category][stat] += new_stats[category][stat]

def display_import_summary(stats, override_db, reset_db, dry_run, is_final_summary=False, current_filename_for_display=None):
    """Display a summary of the import operation."""
    if is_final_summary:
        st.markdown("### 📊 Final Import Summary")
        st.markdown("---    ") # Visual separator
    else:
        # Use the explicitly passed filename for individual summaries if available
        filename_to_show = current_filename_for_display if current_filename_for_display else stats.get('filename', 'Unknown file')
        st.markdown(f"##### 📄 Summary for: *{filename_to_show}*")
    
    # File type and processing mode (only for individual files)
    if not is_final_summary:
        file_type = stats.get('file_type')
        if file_type and file_type != 'Unknown':
            st.markdown(f"**File Type:** {file_type}")
        st.markdown(f"**Processing Mode:** {'Dry Run (Preview)' if dry_run else 'Actual Import'}")
    
    # File & Sheet Details
    sheets = stats.get('sheets', {})
    st.markdown("**📑 Sheet Details:**")
    st.markdown(f"  - Processed: {sheets.get('processed', 0)} of {sheets.get('total', 0)} sheets")
    
    # Row Processing
    rows = stats.get('rows', {})
    st.markdown("**📊 Data Processing:**")
    st.markdown(f"  - Rows Scanned: {rows.get('scanned', 0):,}")
    st.markdown(f"  - Rows Merged/Processed: {rows.get('merged', 0):,}")
    if rows.get('errors', 0) > 0:
        st.markdown(f"  - <span style='color: red;'>Errors Encountered: {rows.get('errors', 0):,}</span>", unsafe_allow_html=True)
    
    # Database Changes (only for final summary or if there are changes and not a dry run)
    actual = stats.get('actual', {})
    if not dry_run and (is_final_summary or any(actual.values())):
        st.markdown("**💾 Database Changes:**")
        st.markdown(f"  - Records Inserted: {actual.get('inserted', 0):,}")
        st.markdown(f"  - Records Replaced: {actual.get('replaced', 0):,}")
        if actual.get('ignored', 0) > 0:
            st.markdown(f"  - Records Ignored: {actual.get('ignored', 0):,}")
    elif dry_run and (is_final_summary or any(actual.values())):
        st.markdown("**Preview of Database Changes (Dry Run):**")
        st.markdown(f"  - Records to be Inserted: {actual.get('inserted', 0):,}")
        st.markdown(f"  - Records to be Replaced: {actual.get('replaced', 0):,}")
        if actual.get('ignored', 0) > 0:
            st.markdown(f"  - Records to be Ignored: {actual.get('ignored', 0):,}")
    st.markdown("---    ") # Visual separator at the end of each summary block

    # Display details of unprocessed sheets if any
    unprocessed_sheets = []
    if is_final_summary:
        unprocessed_sheets = stats.get('unprocessed_sheets_details', [])
    elif 'unprocessed_sheet_info' in stats: # For individual file summaries
        # Structure it similarly for consistent display logic later
        for item in stats['unprocessed_sheet_info']:
            unprocessed_sheets.append({
                'original_filename': current_filename_for_display, # Already available for individual summary
                'sheet_name': item.get('sheet_name', 'Unknown Sheet'),
                'reason': item.get('reason', 'No reason provided')
            })

    if unprocessed_sheets:
        st.markdown("**⚠️ Unprocessed Sheet Details:**")
        for detail in unprocessed_sheets:
            if is_final_summary: # Only show filename in the final summary list
                 st.markdown(f"  - **File:** `{detail['original_filename']}` - **Sheet:** `{detail['sheet_name']}` - **Reason:** {detail['reason']}")
            else: # For individual file summary, filename is already in the header
                 st.markdown(f"  - **Sheet:** `{detail['sheet_name']}` - **Reason:** {detail['reason']}")
        st.markdown("---    ")

def list_gcs_backups():
    """List all backups in Google Cloud Storage with accurate size and proper sorting."""
    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"
        # Get detailed list with size and timestamp
        result = subprocess.run(
            ["gsutil", "ls", "-l", "gs://orionxlog-backups/backups/"],
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        lines = result.stdout.strip().split('\n')
        backup_info = []
        for line in lines:
            if not line or line.startswith('TOTAL:'):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                size = int(parts[0])
                gcs_url = parts[2]
                filename = os.path.basename(gcs_url)
                db_rows_from_filename = "N/A" # Default for parsing

                # Parse date/time and now row count from filename
                # Example new: backup_2025-05-22_16-09-32_UTC_local_rows-123.tar.gz
                # Example old: backup_2025-05-22_16-09-32_UTC_local.tar.gz
                m = re.match(r"backup_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_UTC_([^._]+)(?:_rows-(\d+))?\.tar\.gz", filename)
                
                utc_dt = None
                display_date = filename # Default if parsing fails
                environment = "unknown"

                if m:
                    date_str, time_str, env_str, rows_str = m.groups()
                    # Parse UTC timestamp
                    utc_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H-%M-%S")
                    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                    # Convert to local timezone for display
                    local_dt = utc_dt.astimezone()
                    display_date = local_dt.strftime("%b %d, %Y %H:%M:%S %Z")
                    environment = env_str if env_str else "unknown"
                    if environment not in ['cloud', 'local']:
                        environment = 'unknown' # Validate environment
                    
                    if rows_str:
                        db_rows_from_filename = rows_str
                    else:
                        db_rows_from_filename = "N/A" # For old backups without row count in filename
                else:
                    # Fallback for very old filenames or completely different patterns if any
                    # This part might need adjustment if other filename patterns exist
                    # For now, we assume the primary patterns are caught by the regex above
                    pass # display_date and environment remain as defaults

                backup_info.append({
                    'url': gcs_url,
                    'filename': filename,
                    'datetime': utc_dt,
                    'display_date': display_date,
                    'environment': environment,
                    'size': f"{size/1024/1024:.2f} MB" if size else "unknown", # Keep size for now
                    'db_rows': db_rows_from_filename
                })
            except Exception: # General parsing error for a line
                # This catches errors in processing a single line from gsutil output
                # st.warning(f"Skipping backup line due to parsing error: {line}") # Optional logging
                continue
        
        # Sort backups by UTC datetime, most recent first
        backup_info.sort(key=lambda x: x['datetime'] if x['datetime'] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return backup_info
    except subprocess.CalledProcessError as e:
        st.error(f"Error accessing GCS: {e.stderr}")
        return []
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return []

# Add project root to sys.path for robust imports
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from app.authentication import get_authenticator
from scripts.import_data import import_data
from app.backup_manager import BackupManager
from datetime import datetime, timezone
import pytz

# Initialize backup manager
backup_manager = BackupManager()

# Get authenticator and config
authenticator, config = get_authenticator()

# Check if we're already authenticated
if 'authentication_status' not in st.session_state or st.session_state.authentication_status is None:
    st.error('Please log in from the home page first')
    st.stop()

# Get user info from session state
name = st.session_state.name
username = st.session_state.username

# Check if user is admin
if not config.get('credentials', {}).get('usernames', {}).get(username, {}).get('is_admin', False):
    st.error('Access denied. Admin privileges required.')
    st.stop()

# Show the sidebar after successful authentication
st.markdown("""
    <style>
        section[data-testid="stSidebar"] {
            display: block;
        }
    </style>
""", unsafe_allow_html=True)

# User is authenticated
if authenticator.logout(button_name='Logout', location='sidebar', key='logout-admin'):
    # Clear authentication state
    st.session_state.authentication_status = None
    st.session_state.name = None
    st.session_state.username = None
    st.rerun()

st.sidebar.write(f'Welcome *{name}*')

# Start backup scheduler if not already running
if not hasattr(st.session_state, 'backup_scheduler_started'):
    backup_manager.start_backup_scheduler()
    st.session_state.backup_scheduler_started = True

# Initialize backup list in session state if not exists
if 'backup_list' not in st.session_state:
    st.session_state.backup_list = list_gcs_backups()

# For backup management data editor state
if 'backup_management_editor_key' not in st.session_state:
    st.session_state.backup_management_editor_key = 0
if 'backup_management_df' not in st.session_state:
    st.session_state.backup_management_df = None

st.title("Admin Dashboard")

# Create tabs for different admin functions
tab1, tab2, tab3 = st.tabs(["User Management", "File and Database Management", "Backup Management"])

with tab1:
    st.header("User Management")
    
    # Display current users in a table
    st.subheader("Current Users")
    users = config['credentials']['usernames']
    
    # Create DataFrame for users
    user_data = []
    for username, user_data_dict in users.items():
        user_data.append({
            'Username': username,
            'Name': user_data_dict['name'],
            'Email': user_data_dict['email'],
            'Admin': user_data_dict.get('is_admin', False)
        })
    
    if user_data:
        user_df = pd.DataFrame(user_data)
        # Add checkbox column
        user_df.insert(0, 'Select', False)
        
        # Display users in a table with checkboxes
        edited_df = st.data_editor(
            user_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    help="Select users to act on",
                    default=False
                ),
                "Username": st.column_config.TextColumn(
                    "Username",
                    width="small"
                ),
                "Name": st.column_config.TextColumn(
                    "Name",
                    width="small"
                ),
                "Email": st.column_config.TextColumn(
                    "Email",
                    width="small"
                ),
                "Admin": st.column_config.CheckboxColumn(
                    "Admin",
                    help="Is this user an admin?",
                    default=False
                )
            },
            disabled=["Username", "Name", "Email"]
        )
        
        # Get selected users
        selected_users = [user_df.iloc[i]['Username'] for i, selected in enumerate(edited_df['Select']) if selected]
        
        # Add delete button and logic
        if selected_users:
            if st.button("Delete Selected Users"):
                deleted_any = False
                for username in selected_users:
                    if username == 'admin':
                        st.error("Cannot delete admin user")
                    else:
                        del config['credentials']['usernames'][username]
                        deleted_any = True
                if deleted_any:
                    # Save config after deletion
                    config_path = os.path.abspath(os.path.join('config', 'config.yaml'))
                    with open(config_path, 'w') as file:
                        yaml.dump(config, file)
                    st.success(f"Deleted {len(selected_users)} user(s) (except admin) and updated config.")
                    time.sleep(1)  # Add a small delay to ensure the file is written
                    st.session_state.backup_list = list_gcs_backups()
                    st.rerun()
        
        # Handle admin status changes
        for i, row in edited_df.iterrows():
            username = row['Username']
            new_admin_status = row['Admin']
            if new_admin_status != users[username].get('is_admin', False):
                users[username]['is_admin'] = new_admin_status
                # Always use absolute path for config/config.yaml
                config_path = os.path.abspath(os.path.join('config', 'config.yaml'))
                try:
                    # Save the config
                    with open(config_path, 'w') as file:
                        yaml.dump(config, file)
                    
                    # Small delay to ensure file is written
                    time.sleep(1)
                    
                    # Verify the config was saved
                    if os.path.exists(config_path):
                        with open(config_path, 'r') as file:
                            saved_config = yaml.safe_load(file)
                            if new_username in saved_config.get('credentials', {}).get('usernames', {}):
                                st.success("✅ Configuration saved successfully")
                                # Update the in-memory config so the new user appears immediately
                                users[new_username] = {
                                    'name': new_name,
                                    'email': new_email,
                                    'password': stauth.Hasher([new_password]).generate()[0],
                                    'is_admin': is_admin
                                }
                            else:
                                st.error("❌ Configuration was not saved correctly")
                                st.stop()
                    else:
                        st.error("❌ Configuration file was not found after saving")
                        st.stop()
                    
                    # Create a placeholder for the backup status
                    backup_status = st.empty()
                    
                    # Trigger a backup after adding a user
                    backup_status.info("🔄 Creating backup of updated configuration...")
                    backup_success = backup_manager.run_backup()
                    
                    if backup_success:
                        backup_status.success("✅ Backup completed successfully")
                        st.session_state.backup_list = list_gcs_backups()
                    else:
                        backup_status.warning("⚠️ User was added but backup failed. Please create a manual backup from the Backup Management tab.")
                        st.stop()
                        
                except Exception as e:
                    st.error(f"❌ Error saving configuration: {str(e)}")
                    st.stop()

    # Add new user
    st.subheader("Add New User")
    new_username = st.text_input("Username*")
    new_name = st.text_input("Name*")
    new_email = st.text_input("Email*")
    new_password = st.text_input("Password*", type="password")
    is_admin = st.checkbox("Admin privileges")
    
    if st.button("Add User"):
        error_messages = []
        if not new_username:
            error_messages.append("Username is required.")
        if not new_name:
            error_messages.append("Name is required.")
        if not new_email:
            error_messages.append("Email is required.")
        if not new_password:
            error_messages.append("Password is required.")

        if error_messages:
            for error in error_messages:
                st.error(error)
        elif new_username in config['credentials']['usernames']:
            st.error("Username already exists")
        else:
            config['credentials']['usernames'][new_username] = {
                'name': new_name,
                'email': new_email,
                'password': stauth.Hasher([new_password]).generate()[0],
                'is_admin': is_admin
            }
            # Always use absolute path for config/config.yaml
            config_path = os.path.abspath(os.path.join('config', 'config.yaml'))
            try:
                # Save the config
                with open(config_path, 'w') as file:
                    yaml.dump(config, file)
                
                # Small delay to ensure file is written
                time.sleep(1)
                
                # Verify the config was saved
                if os.path.exists(config_path):
                    with open(config_path, 'r') as file:
                        saved_config = yaml.safe_load(file)
                        if new_username in saved_config.get('credentials', {}).get('usernames', {}):
                            st.success("✅ Configuration saved successfully")
                            # Update the in-memory config so the new user appears immediately
                            users[new_username] = {
                                'name': new_name,
                                'email': new_email,
                                'password': stauth.Hasher([new_password]).generate()[0],
                                'is_admin': is_admin
                            }
                        else:
                            st.error("❌ Configuration was not saved correctly")
                            st.stop()
                else:
                    st.error("❌ Configuration file was not found after saving")
                    st.stop()
                
                # Create a placeholder for the backup status
                backup_status = st.empty()
                
                # Trigger a backup after adding a user
                backup_status.info("🔄 Creating backup of updated configuration...")
                backup_success = backup_manager.run_backup()
                
                if backup_success:
                    backup_status.success("✅ Backup completed successfully")
                    st.session_state.backup_list = list_gcs_backups()
                else:
                    backup_status.warning("⚠️ User was added but backup failed. Please create a manual backup from the Backup Management tab.")
                    st.stop()
                    
            except Exception as e:
                st.error(f"❌ Error saving configuration: {str(e)}")
                st.stop()

with tab2:
    st.header("File and Database Management")
    
    # Initialize GCS file list cache and upload_in_progress in session state
    if 'upload_in_progress' not in st.session_state:
        st.session_state.upload_in_progress = False
    if 'gcs_bucket_files' not in st.session_state:
        st.session_state.gcs_bucket_files = None
    if 'gcs_files_last_refreshed' not in st.session_state:
        st.session_state.gcs_files_last_refreshed = None

    # Initialize session state for import/delete actions
    if 'import_button_pressed' not in st.session_state:
        st.session_state.import_button_pressed = False
    if 'delete_button_pressed' not in st.session_state:
        st.session_state.delete_button_pressed = False
    if 'files_for_action' not in st.session_state:
        st.session_state.files_for_action = []
    if 'import_options' not in st.session_state:
        st.session_state.import_options = {}

    # Session state for file management data editor
    if 'manage_files_editor_key' not in st.session_state:
        st.session_state.manage_files_editor_key = 0
    if 'file_management_df' not in st.session_state:
        st.session_state.file_management_df = None 

    # Initialize session state for batch import if not exists
    if 'multi_batch_import_active' not in st.session_state:
        st.session_state.multi_batch_import_active = False
    if 'gcs_files_for_batch_import' not in st.session_state:
        st.session_state.gcs_files_for_batch_import = []
    if 'batch_import_temp_dir' not in st.session_state:
        st.session_state.batch_import_temp_dir = None
    if 'batch_downloaded_files_map' not in st.session_state:
        st.session_state.batch_downloaded_files_map = {}
    if 'batch_failed_to_download_files' not in st.session_state:
        st.session_state.batch_failed_to_download_files = []
    if 'batch_import_current_idx' not in st.session_state:
        st.session_state.batch_import_current_idx = 0
    if 'batch_import_total_stats' not in st.session_state:
        st.session_state.batch_import_total_stats = {} # Will be properly initialized when an import starts
    if 'batch_import_options' not in st.session_state:
        st.session_state.batch_import_options = {}
    if 'batch_import_initial_setup_done' not in st.session_state:
        st.session_state.batch_import_initial_setup_done = False

    REFRESH_INTERVAL = timedelta(minutes=5)

    # --- GCS File List Loading and Caching ---
    # Button to manually refresh the file list
    if st.button("🔄 Refresh File List from GCS"):
        st.session_state.gcs_bucket_files = None # Force refresh
        st.session_state.gcs_files_last_refreshed = None
        st.rerun()

    # Load or refresh GCS file list if needed
    if st.session_state.gcs_bucket_files is None or \
       (st.session_state.gcs_files_last_refreshed and datetime.now(timezone.utc).replace(tzinfo=timezone.utc) - st.session_state.gcs_files_last_refreshed > REFRESH_INTERVAL):
        with st.spinner("Loading files from GCS bucket..."):
            st.session_state.gcs_bucket_files = list_bucket_files()
            st.session_state.gcs_files_last_refreshed = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
            # No rerun here, allow script to continue and use the freshly loaded list

    files_in_bucket_cache = st.session_state.gcs_bucket_files if st.session_state.gcs_bucket_files is not None else []
    
    # --- Upload Section ---
    st.subheader("📤 Upload New Files")
    st.markdown("""
    Upload Excel files (.xlsx, .xls) to add new data to the system. The system will:
    - Validate file format and content
    - Check for existing files to prevent duplicates
    - Allow you to choose how to handle existing files
    """)
    
    # Add uploader_key to session_state for resetting uploader
    if 'uploader_key' not in st.session_state:
        st.session_state['uploader_key'] = 0

    uploaded_files = st.file_uploader(
        "Choose Excel files (.xlsx, .xls)",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}"
    )
    
    if uploaded_files:
        # Check existing files once using the cached list
        # Ensure cache is loaded if it's somehow None at this point (should be loaded by logic above)
        if st.session_state.gcs_bucket_files is None:
            with st.spinner("Refreshing file list for conflict check..."):
                st.session_state.gcs_bucket_files = list_bucket_files()
                st.session_state.gcs_files_last_refreshed = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
            files_in_bucket_cache = st.session_state.gcs_bucket_files if st.session_state.gcs_bucket_files is not None else []

        existing_names = [f['name'] for f in files_in_bucket_cache]
        
        # Create a DataFrame to display file status
        file_status = []
        has_conflicts = False
        for file in uploaded_files:
            status = 'Already exists' if file.name in existing_names else 'Ready to upload'
            if status == 'Already exists':
                has_conflicts = True
            file_status.append({
                'Filename': file.name,
                'Size': f"{file.size/1024/1024:.2f} MB",
                'Status': status
            })
        
        # Display file status table
        st.dataframe(
            pd.DataFrame(file_status),
            use_container_width=True,
            hide_index=True
        )
        
        # Handle conflicts if any exist
        if has_conflicts:
            st.warning("⚠️ Some files already exist in the bucket.")
            conflict_action = st.radio(
                "How would you like to handle existing files?",
                ["Skip existing files", "Replace existing files"],
                help="Skip: Only upload new files\nReplace: Upload all files, overwriting existing ones",
                key="conflict_radio_choice"
            )
        
        # Single upload button for all files
        if st.button("Upload All Files", disabled=st.session_state.upload_in_progress):
            st.session_state.upload_in_progress = True
            st.rerun() # Rerun to disable the button immediately
            
    if st.session_state.upload_in_progress:
        # This block will execute after the rerun when upload_in_progress is True
        if not uploaded_files: # Check if file selection was lost
            st.warning("File selection was lost. Please re-select files and try again.")
            st.session_state.upload_in_progress = False # Reset flag
            st.session_state.gcs_bucket_files = None # Invalidate cache as a precaution
            st.session_state.gcs_files_last_refreshed = None
            st.rerun()
        else:
            actual_files_to_upload_data = []
            actual_files_to_upload_names = []
            skipped_count = 0
            
            # Determine conflict action and existing files again, as state might be lost on rerun
            # This assumes `has_conflicts` was determined correctly before this block was entered.
            # And `conflict_radio_choice` holds the selection from st.radio.
            current_gcs_files_for_upload = st.session_state.gcs_bucket_files if st.session_state.gcs_bucket_files is not None else []
            existing_names_for_upload = [f['name'] for f in current_gcs_files_for_upload]
            chosen_conflict_action = st.session_state.get("conflict_radio_choice", "Skip existing files")

            progress_placeholder = st.empty()
            progress_placeholder.info(f"Preparing {len(uploaded_files)} selected file(s) for batch upload...")

            for file_data in uploaded_files:
                if file_data.name in existing_names_for_upload and chosen_conflict_action == "Skip existing files":
                    skipped_count += 1
                    st.write(f"Skipping existing file: {file_data.name}") # More immediate feedback
                else:
                    actual_files_to_upload_data.append(file_data)
                    actual_files_to_upload_names.append(file_data.name)
            
            success_count = 0
            error_count = 0

            if actual_files_to_upload_names:
                progress_placeholder.info(f"Starting batch upload of {len(actual_files_to_upload_names)} file(s) to GCS...")
                upload_results = upload_to_bucket(actual_files_to_upload_data, actual_files_to_upload_names)
                success_count = upload_results.get("success", 0)
                error_count = upload_results.get("error", 0)
                # Note: The batch uploader doesn't currently track skipped, assumes files passed are all attempted.
                # The skipped_count here is from the pre-check.
                if success_count > 0:
                    progress_placeholder.success(f"Batch upload processed. {success_count} file(s) reported as successful by gsutil.")
                if error_count > 0:
                    progress_placeholder.error(f"Batch upload processed. {error_count} file(s) reported as failed by gsutil.")
                if success_count == 0 and error_count == 0 and skipped_count == 0 and len(actual_files_to_upload_names) > 0:
                    progress_placeholder.warning("Batch upload command executed but reported no successes or errors for the attempted files.")
            elif skipped_count > 0:
                progress_placeholder.info("No new files to upload after skipping existing ones.")
            else:
                progress_placeholder.info("No files were selected or prepared for upload.")
            
            time.sleep(1) # Brief pause for messages to be read
            progress_placeholder.empty() # Clear the last progress message
            
            # Show detailed results
            if success_count > 0:
                st.success(f"Successfully uploaded {success_count} file(s) in batch.")
            if error_count > 0:
                st.error(f"Failed to upload {error_count} file(s) in batch.")
            if skipped_count > 0:
                st.info(f"Skipped {skipped_count} existing file(s) based on choice.")
            
            if success_count > 0 or error_count > 0 or skipped_count > 0:
                st.session_state['uploader_key'] += 1 # Reset file uploader
            
            st.session_state.upload_in_progress = False # Reset the flag
            st.session_state.gcs_bucket_files = None # Invalidate GCS file cache to reflect new files
            st.session_state.gcs_files_last_refreshed = None
            st.rerun() # Rerun to re-enable button, clear state, and refresh file list
    
    st.markdown("---")
    
    # File Management Section
    st.subheader("📁 Manage Files")
    st.markdown("""
    View and manage your uploaded files. You can:
    - See all files in the system with their details (loaded from cache)
    - Import selected files into the database
    - Delete files you no longer need
    """)
    
    # Use the cached list for "Manage Files" display
    files_for_management = files_in_bucket_cache
    
    # Prepare DataFrame for data_editor, managing its state across reruns
    rebuild_df = False
    if st.session_state.file_management_df is None:
        rebuild_df = True
    else:
        # Check if the number of files changed
        if len(st.session_state.file_management_df) != len(files_for_management):
            rebuild_df = True
        # Check if the filenames themselves changed (order matters here, but GCS list is sorted by date)
        elif set(st.session_state.file_management_df['Filename']) != set(f['name'] for f in files_for_management):
            rebuild_df = True

    if rebuild_df:
        if files_for_management: # Only build if there are files from GCS
            temp_df = pd.DataFrame(files_for_management)
            temp_df = temp_df[['name', 'display_date', 'size_display']]
            temp_df.columns = ['Filename', 'Upload Date', 'Size']
            temp_df.insert(0, 'Select', False) # Initialize Select column
            st.session_state.file_management_df = temp_df.copy() # Store a copy
        else: # No files from GCS, create an empty placeholder
             st.session_state.file_management_df = pd.DataFrame(columns=['Select', 'Filename', 'Upload Date', 'Size']) # Empty DF is fine as is

    # Ensure file_management_df is not None before trying to check if it's empty
    if st.session_state.file_management_df is not None and not st.session_state.file_management_df.empty:
        # "Select All" / "Deselect All" buttons
        col_select_all, col_deselect_all = st.columns(2)
        with col_select_all:
            if st.button("Select All Files", key="select_all_manage_files"):
                st.session_state.file_management_df['Select'] = True
                st.session_state.manage_files_editor_key += 1
                st.rerun()
        with col_deselect_all:
            if st.button("Deselect All Files", key="deselect_all_manage_files"):
                st.session_state.file_management_df['Select'] = False
                st.session_state.manage_files_editor_key += 1
                st.rerun()

        # Snapshot the DataFrame before passing it to the editor for change detection
        df_snapshot_before_editor = st.session_state.file_management_df.copy()

        # The editor is given the DataFrame from session state directly.
        # Its return value (the potentially modified DataFrame) is captured.
        edited_df_output = st.data_editor(
            st.session_state.file_management_df, 
            use_container_width=True,
            hide_index=True,
            key=f"file_management_data_editor_{st.session_state.manage_files_editor_key}", 
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    help="Select files to act on",
                    default=False
                ),
                "Filename": st.column_config.TextColumn(
                    "Filename",
                    width="medium"
                ),
                "Upload Date": st.column_config.TextColumn(
                    "Upload Date",
                    width="medium"
                ),
                "Size": st.column_config.TextColumn(
                    "Size",
                    width="small"
                )
            },
            disabled=["Filename", "Upload Date", "Size"]
        )
        
        # Update our primary session state DataFrame with the output from the editor
        # Make sure to use a copy to prevent unintended side effects with mutable DataFrames
        st.session_state.file_management_df = edited_df_output.copy()

        # Now, check if the editor interaction actually changed the DataFrame's content
        # by comparing the snapshot with the current state of st.session_state.file_management_df
        if not df_snapshot_before_editor.equals(st.session_state.file_management_df):
            # If a change occurred (e.g., a checkbox was ticked/unticked by the user),
            # increment the key to force a full remount of the editor in the next run,
            # and trigger that rerun.
            st.session_state.manage_files_editor_key += 1
            st.rerun()
        
        # Get selected files from the (potentially updated and re-keyed) session state DataFrame
        selected_files_from_editor = [
            st.session_state.file_management_df.iloc[i]['Filename'] 
            for i, selected in enumerate(st.session_state.file_management_df['Select']) if selected
        ]
        
        if selected_files_from_editor:
            st.markdown("### Selected Files Actions")
            
            # Import options
            st.markdown("#### Import Options")
            st.markdown("""
            **Database Update Options:**
            - These options control how the new data will be integrated with existing data in the database
            """)
            
            override_db_checkbox = st.checkbox(
                "Update existing data for the same month/year",
                help="If checked, new data will replace existing data for the same time period. Recommended for normal updates."
            )
            
            reset_db_checkbox = st.checkbox(
                "Clear all existing data before import",
                help="⚠️ WARNING: This will delete ALL existing data in the database before importing. Use with extreme caution!"
            )
            
            if reset_db_checkbox:
                st.warning("""
                ⚠️ **Danger Zone**: You have selected to clear all existing data.
                - This will permanently delete ALL data currently in the database
                - Only the first file in your selection will trigger this reset
                - Make sure you have a backup before proceeding
                """)
            
            perform_dry_run_checkbox = st.checkbox(
                "Preview changes without saving",
                help="If checked, the import will be simulated without making any changes to the database. Useful for testing."
            )
            
            col3, col4 = st.columns(2)
            
            with col3:
                if st.button("Import Selected Files"):
                    st.session_state.files_for_action = selected_files_from_editor
                    st.session_state.import_options = {
                        'override_db': override_db_checkbox,
                        'reset_db': reset_db_checkbox,
                        'perform_dry_run': perform_dry_run_checkbox
                    }
                    st.session_state.import_button_pressed = True
                    st.session_state.delete_button_pressed = False # Ensure only one action runs
                    st.rerun()
            
            with col4:
                if st.button("Delete Selected Files"):
                    st.session_state.files_for_action = selected_files_from_editor
                    st.session_state.delete_button_pressed = True
                    st.session_state.import_button_pressed = False # Ensure only one action runs
                    st.rerun()
    else:
        st.info("No files found in the GCS bucket (or cache is empty). Try refreshing the list or upload some files.")

    # --- Processing Blocks (Full Width) ---
    # This section will now handle the new batch import logic
    BATCH_SIZE = 25

    if st.session_state.get('import_button_pressed') and not st.session_state.multi_batch_import_active:
        # ---- START OF A NEW MULTI-BATCH IMPORT ----
        selected_gcs_files = st.session_state.files_for_action
        import_options = st.session_state.import_options

        if not selected_gcs_files:
            st.warning("No files were selected for import.")
            st.session_state.import_button_pressed = False # Reset button state
        else:
            st.info(f"Initializing import for {len(selected_gcs_files)} file(s)...")
            # Create a persistent temporary directory for this entire multi-batch operation
            try:
                st.session_state.batch_import_temp_dir = tempfile.mkdtemp(prefix="orionxlog_batch_import_")
                st.write(f"DEBUG: Created persistent temp dir: {st.session_state.batch_import_temp_dir}") # DEBUG
            except Exception as e:
                st.error(f"Failed to create temporary directory for batch import: {e}")
                st.session_state.import_button_pressed = False
                # No rerun, allow user to see error.
                # Make sure to clean up any partial state if needed later.
                st.stop() # Stop execution to prevent further issues

            st.session_state.multi_batch_import_active = True
            st.session_state.gcs_files_for_batch_import = selected_gcs_files
            st.session_state.batch_import_options = import_options
            st.session_state.batch_import_current_idx = 0
            st.session_state.batch_import_total_stats = {
                'filename': 'Multiple Files (Batch Import)',
                'sheets': {'processed': 0, 'total': 0},
                'rows': {'scanned': 0, 'merged': 0, 'errors': 0},
                'actual': {'inserted': 0, 'replaced': 0, 'ignored': 0},
                'unprocessed_sheets_details': []
            }
            st.session_state.batch_downloaded_files_map = {}
            st.session_state.batch_failed_to_download_files = []
            st.session_state.batch_import_initial_setup_done = False # Will be set after download & initial DB ops

            st.session_state.import_button_pressed = False # Reset the trigger
            st.rerun() # Rerun to enter the active batch processing logic below

    if st.session_state.multi_batch_import_active:
        # ---- ACTIVE MULTI-BATCH IMPORT PROCESSING ----
        gcs_files_to_process_overall = st.session_state.gcs_files_for_batch_import
        temp_dir_for_this_run = st.session_state.batch_import_temp_dir
        current_idx = st.session_state.batch_import_current_idx
        options = st.session_state.batch_import_options
        total_stats = st.session_state.batch_import_total_stats
        
        override_db = options.get('override_db', False)
        reset_db = options.get('reset_db', False)
        perform_dry_run = options.get('perform_dry_run', False)

        status_text_area = st.empty()
        progress_bar_area = st.empty()

        if not temp_dir_for_this_run or not os.path.exists(temp_dir_for_this_run):
            st.error("Critical error: Batch import temporary directory is missing. Aborting.")
            # Reset state to allow starting over
            st.session_state.multi_batch_import_active = False
            st.session_state.batch_import_initial_setup_done = False
            if temp_dir_for_this_run and os.path.exists(temp_dir_for_this_run): # Defensive cleanup
                try: shutil.rmtree(temp_dir_for_this_run) 
                except: pass
            st.session_state.batch_import_temp_dir = None
            st.rerun()

        try:
            if not st.session_state.batch_import_initial_setup_done:
                status_text_area.info("Performing initial setup: DB operations and batch file download...")
                # 1. One-time DB backup and reset (if configured)
                if not perform_dry_run and os.path.exists(database_file_path):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    initial_backup_path = os.path.join(backups_dir, f"podcasts_pre_batch_import_{timestamp}.db")
                    shutil.copy2(database_file_path, initial_backup_path)
                    st.success(f"Created pre-batch import backup of current database: {initial_backup_path}")
                
                if reset_db and not perform_dry_run:
                    if os.path.exists(database_file_path):
                        os.remove(database_file_path)
                        st.info("Database has been reset before batch import starts.")
                    else:
                        st.info("Database file not found, so no reset needed.")

                # 2. Download all GCS files to the persistent temporary directory
                with st.spinner(f"Downloading {len(gcs_files_to_process_overall)} file(s) from GCS..."):
                    downloaded_map, failed_list = batch_download_from_bucket(gcs_files_to_process_overall, temp_dir_for_this_run)
                    st.session_state.batch_downloaded_files_map = downloaded_map
                    st.session_state.batch_failed_to_download_files = failed_list

                if st.session_state.batch_failed_to_download_files:
                    st.warning(f"{len(st.session_state.batch_failed_to_download_files)} file(s) could not be downloaded and will be skipped:")
                    for failed_file in st.session_state.batch_failed_to_download_files:
                        st.write(f"- {failed_file}")
                
                st.session_state.batch_import_initial_setup_done = True
                # We will process the first batch in this same run, so don't rerun yet unless no files downloaded
                if not st.session_state.batch_downloaded_files_map:
                    status_text_area.warning("No files were successfully downloaded. Nothing to import.")
                    # Clean up and end batch mode
                    if os.path.exists(temp_dir_for_this_run): shutil.rmtree(temp_dir_for_this_run)
                    st.session_state.batch_import_temp_dir = None
                    st.session_state.multi_batch_import_active = False
                    st.session_state.batch_import_initial_setup_done = False 
                    st.rerun()
                    st.stop() # Should not be reached due to rerun
            
            # Determine files for the current actual processing batch
            successfully_downloaded_gcs_filenames = list(st.session_state.batch_downloaded_files_map.keys())
            files_for_this_processing_batch = successfully_downloaded_gcs_filenames[current_idx : current_idx + BATCH_SIZE]

            if not files_for_this_processing_batch and current_idx >= len(successfully_downloaded_gcs_filenames) and len(successfully_downloaded_gcs_filenames) > 0:
                # All files have been processed in previous batches
                pass # Will proceed to finalization logic
            elif not files_for_this_processing_batch and current_idx == 0 and not successfully_downloaded_gcs_filenames:
                # This case handled by the initial download check, but as a safeguard
                status_text_area.info("No files available to process.")
            else:
                status_text_area.info(f"Processing batch: files {current_idx + 1} to {min(current_idx + BATCH_SIZE, len(successfully_downloaded_gcs_filenames))} of {len(successfully_downloaded_gcs_filenames)} downloaded files.")
                for i, gcs_filename in enumerate(files_for_this_processing_batch):
                    local_filepath = st.session_state.batch_downloaded_files_map[gcs_filename]
                    loop_progress_idx = current_idx + i
                    status_text_area.text(f"Importing: {gcs_filename} ({loop_progress_idx + 1}/{len(successfully_downloaded_gcs_filenames)} of downloaded files)..." )
                    progress_bar_area.progress((loop_progress_idx + 1) / len(successfully_downloaded_gcs_filenames))

                    try:
                        if os.path.exists(local_filepath) and os.path.getsize(local_filepath) > 0:
                            stats = import_data(
                                filepath=local_filepath,
                                override=override_db,
                                dry_run=perform_dry_run,
                                reset_db=False, # Handled once at the start
                                skip_backup=True, # Handled once at start and once at end
                                original_filename=gcs_filename
                            )
                            if stats:
                                accumulate_stats(total_stats, stats) 
                                # Individual file summary can be verbose; consider removing or making it optional for batch mode
                                # with st.expander(f"Details for {gcs_filename}", expanded=False):
                                #    display_import_summary(stats, override_db, reset_db, perform_dry_run, is_final_summary=False, current_filename_for_display=gcs_filename)
                            else:
                                st.error(f"Failed to get import statistics for {gcs_filename}.")
                        else:
                            st.error(f"File {gcs_filename} (local: {local_filepath}) not found or is empty during processing batch.")
                    except Exception as e:
                        st.error(f"Error processing {gcs_filename} from {local_filepath}: {e}")
                
                st.session_state.batch_import_current_idx += len(files_for_this_processing_batch)

            # Check if all files have been processed
            if st.session_state.batch_import_current_idx >= len(successfully_downloaded_gcs_filenames):
                # ---- FINALIZATION OF MULTI-BATCH IMPORT ----
                status_text_area.success("All batches processed!")
                progress_bar_area.empty()
                
                display_import_summary(total_stats, override_db, reset_db, perform_dry_run, is_final_summary=True)
                
                if not perform_dry_run and len(successfully_downloaded_gcs_filenames) > 0:
                    status_text_area.info("Creating final backup of updated data...")
                    if backup_manager.run_backup():
                        st.success("Final backup completed successfully")
                        st.session_state.backup_list = list_gcs_backups()
                    else:
                        st.warning("Final backup failed, but data import (if any) was successful.")
                
                # Clean up persistent temporary directory
                if temp_dir_for_this_run and os.path.exists(temp_dir_for_this_run):
                    try:
                        shutil.rmtree(temp_dir_for_this_run)
                        st.write(f"DEBUG: Removed persistent temp dir: {temp_dir_for_this_run}") # DEBUG
                    except Exception as e:
                        st.warning(f"Could not remove batch import temporary directory {temp_dir_for_this_run}: {e}")
                
                # Reset batch import state
                st.session_state.multi_batch_import_active = False
                st.session_state.gcs_files_for_batch_import = []
                st.session_state.batch_import_temp_dir = None
                st.session_state.batch_downloaded_files_map = {}
                st.session_state.batch_failed_to_download_files = []
                st.session_state.batch_import_current_idx = 0
                st.session_state.batch_import_total_stats = {}
                st.session_state.batch_import_options = {}
                st.session_state.batch_import_initial_setup_done = False
                st.info("Batch import process complete.")
                # No rerun here, allow user to see final messages.
            else:
                # More batches to process
                status_text_area.info(f"Batch complete. Preparing for next batch...")
                time.sleep(1) # Brief pause for user to see message
                st.rerun() # Trigger next batch processing cycle

        except Exception as e:
            st.error(f"An critical error occurred during the batch import process: {e}")
            st.warning("Batch import process aborted due to an unexpected error. Please check logs.")
            # Attempt to clean up and reset state
            if st.session_state.batch_import_temp_dir and os.path.exists(st.session_state.batch_import_temp_dir):
                try: shutil.rmtree(st.session_state.batch_import_temp_dir) 
                except: pass
            st.session_state.multi_batch_import_active = False
            st.session_state.gcs_files_for_batch_import = []
            st.session_state.batch_import_temp_dir = None
            st.session_state.batch_downloaded_files_map = {}
            st.session_state.batch_failed_to_download_files = []
            st.session_state.batch_import_current_idx = 0
            st.session_state.batch_import_total_stats = {}
            st.session_state.batch_import_options = {}
            st.session_state.batch_import_initial_setup_done = False
            st.rerun()

    if st.session_state.get('delete_button_pressed'):
        files_to_delete = st.session_state.files_for_action
        
        if not files_to_delete:
            st.warning("No files were selected for deletion.")
            st.session_state.delete_button_pressed = False # Reset state
            st.session_state.files_for_action = []
            # No rerun needed if nothing to do, just clear flags.
        else:
            st.info(f"Batch deletion process started for {len(files_to_delete)} file(s)...")
            progress_placeholder = st.empty() # For potential detailed progress if needed in future
            progress_placeholder.text(f"Attempting to delete {len(files_to_delete)} file(s) using a batch command...")

            delete_results = delete_from_bucket(files_to_delete)
            success_count = delete_results.get("success", 0)
            error_count = delete_results.get("error", 0)

            progress_placeholder.empty()

            if success_count > 0:
                st.success(f"Successfully deleted {success_count} file(s) in batch from GCS.")
            if error_count > 0:
                # The error message from delete_from_bucket (st.error) would have already appeared.
                # This is a summary count.
                st.warning(f"Batch delete command indicated {error_count} file(s) could not be deleted or an error occurred.")
            
            if success_count > 0 or error_count > 0:
                st.session_state.gcs_bucket_files = None 
                st.session_state.gcs_files_last_refreshed = None
                # Reset state BEFORE rerun
                st.session_state.delete_button_pressed = False
                st.session_state.files_for_action = []
                st.rerun() 
            else: # No successes or errors reported, but files were selected
                st.info("Delete command processed but reported no changes. Check GCS console if files still exist.")
                st.session_state.delete_button_pressed = False
                st.session_state.files_for_action = []
                # Optionally rerun to clear selection, or allow user to try again
                st.rerun()
        
        # Fallback reset if somehow not covered (e.g., no files selected initially)
        if st.session_state.delete_button_pressed: # Check if still true
            st.session_state.delete_button_pressed = False
            st.session_state.files_for_action = []

with tab3:
    st.header("Backup Management")
    
    # Manual backup trigger at the top
    st.subheader("Create Manual Backup")
    if st.button("Create Manual Backup"):
        with st.spinner("Creating backup..."):
            if backup_manager.run_backup():
                st.success("Manual backup completed successfully")
                # Refresh backup list after successful backup
                st.session_state.backup_list = list_gcs_backups()
                st.session_state.backup_management_df = None # Force DF rebuild
            else:
                st.error("Manual backup failed")
    
    st.markdown("---") # Separator
    st.subheader("Manage Backups in GCS")
    # List backups - ensure it's up-to-date or refresh if needed
    # (Consider adding a refresh button here if list_gcs_backups is not called frequently enough elsewhere)
    backups_from_gcs = st.session_state.get('backup_list', []) # Use the cached list
    if not backups_from_gcs: # If cache is empty or None, try to load
        with st.spinner("Refreshing backup list from GCS..."):
            st.session_state.backup_list = list_gcs_backups()
            backups_from_gcs = st.session_state.backup_list
            st.session_state.backup_management_df = None # Force DF rebuild since list was reloaded

    # Prepare DataFrame for data_editor, managing its state across reruns
    rebuild_backup_df = False
    if st.session_state.backup_management_df is None:
        rebuild_backup_df = True
    else:
        # Check if the number of backups changed
        if len(st.session_state.backup_management_df) != len(backups_from_gcs):
            rebuild_backup_df = True
        # Check if the filenames themselves changed (more robust check needed if order isn't guaranteed)
        elif set(st.session_state.backup_management_df['Filename']) != set(b['filename'] for b in backups_from_gcs):
            rebuild_backup_df = True

    if rebuild_backup_df:
        if backups_from_gcs:
            temp_backup_df = pd.DataFrame(backups_from_gcs)
            # Ensure the DataFrame maintains the sorted order from list_gcs_backups (most recent first)
            temp_backup_df = temp_backup_df[['filename', 'display_date', 'environment', 'db_rows']]
            temp_backup_df.columns = ['Filename', 'Date & Time', 'Environment', 'DB Rows']
            temp_backup_df.insert(0, 'Select', False) # Initialize Select column
            st.session_state.backup_management_df = temp_backup_df.copy()
        else:
            st.session_state.backup_management_df = pd.DataFrame(columns=['Select', 'Filename', 'Date & Time', 'Environment', 'DB Rows'])

    if st.session_state.backup_management_df is not None and not st.session_state.backup_management_df.empty:
        st.write(f"Found {len(backups_from_gcs)} backups:")

        # "Select All" / "Deselect All" buttons for backups
        col_select_all_backups, col_deselect_all_backups = st.columns(2)
        with col_select_all_backups:
            if st.button("Select All Backups", key="select_all_backup_files"):
                st.session_state.backup_management_df['Select'] = True
                st.session_state.backup_management_editor_key += 1
                st.rerun()
        with col_deselect_all_backups:
            if st.button("Deselect All Backups", key="deselect_all_backup_files"):
                st.session_state.backup_management_df['Select'] = False
                st.session_state.backup_management_editor_key += 1
                st.rerun()

        df_snapshot_before_backup_editor = st.session_state.backup_management_df.copy()
        
        edited_backup_df = st.data_editor(
            st.session_state.backup_management_df,
            use_container_width=True,
            hide_index=True,
            key=f"backup_management_data_editor_{st.session_state.backup_management_editor_key}",
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    help="Select backups to act on",
                    default=False,
                ),
                "Filename": st.column_config.TextColumn(
                    "Filename",
                    width="medium",
                ),
                "Date & Time": st.column_config.TextColumn(
                    "Date & Time",
                    width="medium",
                ),
                "Environment": st.column_config.TextColumn(
                    "Environment",
                    width="small",
                ),
                "DB Rows": st.column_config.TextColumn(
                    "DB Rows",
                    help="Number of rows in the podcasts table of the backup (N/A for older backups)",
                    width="small",
                )
            },
            disabled=["Filename", "Date & Time", "Environment", "DB Rows"],
        )
        
        st.session_state.backup_management_df = edited_backup_df.copy()

        if not df_snapshot_before_backup_editor.equals(st.session_state.backup_management_df):
            st.session_state.backup_management_editor_key += 1
            st.rerun()

        # Get selected backups from the editor's output (which is now in session state)
        selected_backup_filenames_from_editor = [
            st.session_state.backup_management_df.iloc[i]['Filename'] 
            for i, selected in enumerate(st.session_state.backup_management_df['Select']) if selected
        ]
        # Map filenames back to the full backup objects for actions
        selected_backups_for_action = [b for b in backups_from_gcs if b['filename'] in selected_backup_filenames_from_editor]

    else:
        st.info("No backups found in GCS (or cache is empty/being refreshed).")
        selected_backups_for_action = [] # Ensure it's defined if there are no backups
    
    # --- EXAMINE PANEL --- (Operates on selected_backups_for_action)
    st.markdown("---")
    st.subheader("Examine Backup")
    if len(selected_backups_for_action) == 1:
        if st.button("Examine Selected Backup", key="examine_selected_backup_btn"):
            import tempfile, sqlite3, tarfile
            import pathlib # pathlib was imported but not used, keeping it for now if needed later
            st.info(f"Examining backup: {selected_backups_for_action[0]['filename']}")
            try:
                env = os.environ.copy()
                env["CLOUDSDK_PYTHON"] = "python3.11"
                with tempfile.TemporaryDirectory() as tmpdir:
                    temp_file_examine = os.path.join(tmpdir, "selected_backup_examine.tar.gz")
                    subprocess.run([
                        "gsutil", "cp", selected_backups_for_action[0]['url'], temp_file_examine
                    ], check=True, env=env, capture_output=True, text=True)
                    # Extract all files
                    with tarfile.open(temp_file_examine, "r:gz") as tar:
                        tar.extractall(path=tmpdir)
                    
                    # Check for config file
                    config_found = False
                    config_path_examine = None
                    for root, dirs, files in os.walk(tmpdir):
                        if "config.yaml" in files:
                            config_path_examine = os.path.join(root, "config.yaml")
                            config_found = True
                            break
                    
                    if config_found:
                        st.info("✅ Config file found in backup")
                        with open(config_path_examine, 'r') as f:
                            config_content = yaml.safe_load(f)
                            num_users = len(config_content.get('credentials', {}).get('usernames', {}))
                            st.info(f"Total users in backup config: {num_users}")
                    else:
                        st.error("❌ Config file not found in backup!")
                    
                    # Check for database
                    db_path_examine = None
                    for root, dirs, files in os.walk(tmpdir):
                        if "podcasts.db" in files:
                            db_path_examine = os.path.join(root, "podcasts.db")
                            break
                    
                    if db_path_examine and os.path.exists(db_path_examine):
                        conn = sqlite3.connect(db_path_examine)
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                        tables = [row[0] for row in cur.fetchall()]
                        st.write("### Database Contents")
                        st.write(f"Tables in backup: {tables}")
                        for table in tables:
                            try:
                                cur.execute(f"SELECT COUNT(*) FROM {table};")
                                count = cur.fetchone()[0]
                                st.write(f"Table `{table}`: {count} rows")
                            except Exception as e:
                                st.write(f"Table `{table}`: error counting rows ({e})")
                        conn.close()
                    else:
                        st.warning("No podcasts.db found in backup archive after extraction.")
            except subprocess.CalledProcessError as spe:
                st.error(f"Error examining backup (command failed): {spe.stderr}")
            except Exception as e:
                st.warning(f"Could not examine backup: {e}")
    elif len(selected_backups_for_action) > 1:
        st.warning("Please select only one backup to examine.")
    else:
        st.info("Select a single backup from the table above to examine its details.")
    
    # --- DELETE PANEL --- (Operates on selected_backups_for_action)
    st.markdown("---")
    st.subheader("Delete Backups")
    if selected_backups_for_action:
        st.warning(f"{len(selected_backups_for_action)} backup(s) selected for deletion.")
        confirm_delete_backups_checkbox = st.checkbox("I understand this will permanently delete the selected backups from GCS.", key="confirm_delete_backups_checkbox")
        
        if st.button("Delete Selected Backups from GCS", key="delete_selected_backups_btn"):
            if confirm_delete_backups_checkbox:
                env = os.environ.copy()
                env["CLOUDSDK_PYTHON"] = "python3.11"
                gcs_urls_to_delete = [backup['url'] for backup in selected_backups_for_action]
                
                if not gcs_urls_to_delete:
                    st.warning("No backup URLs found for deletion (this shouldn't happen if files were selected).")
                else:
                    progress_placeholder_delete = st.empty()
                    progress_placeholder_delete.info(f"Attempting to delete {len(gcs_urls_to_delete)} backup(s) using a batch command...")
                    
                    try:
                        # Command: gsutil -m rm gs://bucket/backup1.tar.gz gs://bucket/backup2.tar.gz ...
                        cmd_delete = ["gsutil", "-m", "rm"] + gcs_urls_to_delete
                        
                        result_delete = subprocess.run(
                            cmd_delete,
                            capture_output=True,
                            text=True,
                            check=False, # Check stderr and return code manually for -m
                            env=env
                        )
                        
                        # gsutil -m rm usually exits with 0 if all operations are successful or if some files specified didn't exist.
                        # It exits with non-zero if there was a more serious error or if some files that did exist could not be removed.
                        # A robust check would parse stderr for "Removing gs://..." and "Problem removing gs://..."
                        # For simplicity, we'll assume success if returncode is 0 and check stderr for explicit problem reports.
                        
                        failed_deletions = 0
                        if result_delete.returncode != 0 or "Problem removing" in result_delete.stderr:
                            # Count how many might have failed based on "Problem removing" or if the command itself errored.
                            # This is an approximation unless we parse each line.
                            # If command failed broadly, assume all failed.
                            if result_delete.returncode != 0:
                                failed_deletions = len(gcs_urls_to_delete)
                                st.error(f"Batch GCS delete command failed. Exit code: {result_delete.returncode}. Stderr: {result_delete.stderr[:500]}...")
                            else: # returncode 0 but "Problem removing" in stderr means partial failure
                                # This part is tricky without specific gsutil output format guarantees
                                # We will rely on user checking GCS for now in this specific partial failure case
                                st.warning(f"gsutil reported some issues during batch delete. Some files may not have been deleted. Stderr: {result_delete.stderr[:500]}...")
                                # To be more precise, one would count "Problem removing" lines.
                                # For now, we can't accurately say how many failed vs succeeded in this mixed scenario from `gsutil -m` easily.
                                # We will assume all were attempted, and if stderr has problems, some failed.
                                # Let's count successful ones as total - those with "Problem removing". This is a basic heuristic.
                                problem_lines = [line for line in result_delete.stderr.splitlines() if "Problem removing" in line]
                                failed_deletions = len(problem_lines)

                        succeeded_deletions = len(gcs_urls_to_delete) - failed_deletions

                        progress_placeholder_delete.empty()

                        if succeeded_deletions > 0:
                            st.success(f"Successfully initiated deletion for {succeeded_deletions} backup(s) (or they were already gone).")
                        if failed_deletions > 0:
                            st.error(f"{failed_deletions} backup(s) may have failed to delete or encountered an issue.")
                        if succeeded_deletions == 0 and failed_deletions == 0 and gcs_urls_to_delete: # Command ran, no errors, no successes reported
                            st.info("Batch delete command ran, but gsutil reported no specific successes or failures. Please verify in GCS.")

                        # Refresh backup list from GCS and editor state
                        st.session_state.backup_list = list_gcs_backups()
                        st.session_state.backup_management_df = None # Force DF rebuild
                        st.session_state.backup_management_editor_key +=1 # Refresh editor
                        st.rerun()
                            
                    except FileNotFoundError: # gsutil not found
                        progress_placeholder_delete.empty()
                        st.error("gsutil command not found. Please ensure Google Cloud SDK is installed and in PATH.")
                    except Exception as e_delete:
                        progress_placeholder_delete.empty()
                        st.error(f"Unexpected error during batch GCS backup delete: {str(e_delete)}")
            else:
                st.warning("Please confirm deletion by checking the box above.")
    else:
        st.info("Select one or more backups from the table above to enable the delete option.")
    
    # --- RESTORE PANEL --- (Operates on selected_backups_for_action)
    st.markdown("---")
    st.subheader("Restore Backup")

    if len(selected_backups_for_action) == 1:
        backup_to_restore = selected_backups_for_action[0]
        st.info(f"Selected for restore: {backup_to_restore['filename']} ({backup_to_restore['environment']}, DB Rows: {backup_to_restore['db_rows']})")
        if st.button(f"Restore Backup: {backup_to_restore['filename']}", key="restore_selected_backup_btn"):
            try:
                with st.spinner(f"Restoring backup: {backup_to_restore['filename']}..."):
                    env = os.environ.copy()
                    env["CLOUDSDK_PYTHON"] = "python3.11"
                    
                    # Determine restore directory based on environment
                    restore_base_dir = data_dir # Use data_dir defined at the top
                    config_base_dir = os.path.abspath(os.path.join('.', 'config')) # Relative to app root for config
                    if os.path.exists("/app/data"): # Cloud specific paths if needed
                        restore_base_dir = "/app/data"
                        config_base_dir = "/app/config" 
                    
                    # Create temp directory for extraction inside the workspace or a known writable area
                    # Using tempfile.TemporaryDirectory for safer management
                    with tempfile.TemporaryDirectory(prefix="orionx_restore_") as temp_dir_restore:
                        temp_archive_path = os.path.join(temp_dir_restore, "selected_backup_to_restore.tar.gz")
                        
                        # Download
                        dl_result = subprocess.run(
                            ["gsutil", "cp", backup_to_restore['url'], temp_archive_path],
                            check=True,
                            env=env,
                            capture_output=True, text=True
                        )
                        
                        # Extract to a sub-directory within the temp directory
                        extract_target_dir = os.path.join(temp_dir_restore, "extracted_content")
                        os.makedirs(extract_target_dir, exist_ok=True)
                        
                        tar_result = subprocess.run(
                            ["tar", "-xzf", temp_archive_path, "-C", extract_target_dir],
                            check=True,
                            capture_output=True, text=True
                        )
                        
                        # Find and move files
                        db_found_in_restore = False
                        config_found_in_restore = False
                        items_moved_count = 0

                        for root, dirs, files_in_root in os.walk(extract_target_dir):
                            if "podcasts.db" in files_in_root:
                                src_db = os.path.join(root, "podcasts.db")
                                dest_db = os.path.join(restore_base_dir, "podcasts.db")
                                os.makedirs(os.path.dirname(dest_db), exist_ok=True)
                                # Backup existing DB before overwriting
                                if os.path.exists(dest_db):
                                    backup_existing_db_path = dest_db + f".backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                                    shutil.move(dest_db, backup_existing_db_path)
                                    st.info(f"Backed up existing database to: {backup_existing_db_path}")
                                shutil.move(src_db, dest_db)
                                db_found_in_restore = True
                                items_moved_count += 1
                            
                            if "config.yaml" in files_in_root:
                                src_config = os.path.join(root, "config.yaml")
                                dest_config = os.path.join(config_base_dir, "config.yaml")
                                os.makedirs(os.path.dirname(dest_config), exist_ok=True)
                                # Backup existing config before overwriting
                                if os.path.exists(dest_config):
                                    backup_existing_config_path = dest_config + f".backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                                    shutil.move(dest_config, backup_existing_config_path)
                                    st.info(f"Backed up existing config to: {backup_existing_config_path}")
                                shutil.move(src_config, dest_config)
                                if not os.name == 'nt': # Skip chmod on Windows
                                    os.chmod(dest_config, 0o600) # Ensure correct permissions
                                config_found_in_restore = True
                                items_moved_count += 1
                        
                        # Temp directory and its contents (downloaded archive, extracted files not moved) are auto-cleaned by TemporaryDirectory context manager

                        if items_moved_count == 0:
                            st.error("Restore process ran, but no 'podcasts.db' or 'config.yaml' were found in the backup archive.")
                        else:
                            if db_found_in_restore:
                                st.success(f"Successfully restored database from backup: {backup_to_restore['display_date']}")
                            else:
                                st.warning("Database (podcasts.db) was NOT found in the backup archive.")
                            
                            if config_found_in_restore:
                                st.success("Config file (config.yaml) was also restored from backup.")
                                st.warning("IMPORTANT: Config file has been restored. You will be logged out. Please REFRESH your browser page to apply changes and log back in.")
                                # Force a full reset of authentication state for security and consistency
                                for key in list(st.session_state.keys()):
                                    if key in ['authentication_status', 'name', 'username', 'authenticator', 'config']:
                                        del st.session_state[key]
                                # Set a flag that login is required, if your app uses such a flag elsewhere.
                                # st.session_state.login_required = True # Example
                                st.stop() # Stop execution to force user to refresh and re-login
                            else:
                                st.warning("Config file (config.yaml) was NOT found in the backup archive.")

            except subprocess.CalledProcessError as spe:
                st.error(f"Error during restore (command execution failed): {spe.stderr}")
                if spe.stdout:
                    st.error(f"Stdout: {spe.stdout}")
            except Exception as e:
                st.error(f"Error restoring backup: {str(e)}")
    elif len(selected_backups_for_action) > 1:
        st.warning("Please select only one backup to restore.")
    else: # 0 selected, or if 'backups_from_gcs' itself is empty
        if not backups_from_gcs:
            st.info("No backups found in Cloud Storage yet.")
        else:
            st.info("Select a single backup from the table above to enable the restore option.")

    # The old selectbox-based restore logic is now removed.