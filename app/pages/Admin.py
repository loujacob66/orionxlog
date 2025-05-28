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

# Define directory paths
if os.path.exists("/app/data"):
    # Cloud environment
    backups_dir = os.path.join("/app/data", "backups")
    permanent_upload_dir = os.path.join("/app/data", "uploaded")
else:
    # Local environment
    backups_dir = os.path.join("data", "backups")
    permanent_upload_dir = os.path.join("data", "uploaded")

# Create directories if they don't exist
os.makedirs(backups_dir, exist_ok=True)
os.makedirs(permanent_upload_dir, exist_ok=True)

# GCS bucket configuration
BUCKET_NAME = "orionxlog-uploaded-files"
BUCKET_URL = f"gs://{BUCKET_NAME}"

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

def upload_to_bucket(file_data, filename):
    """Upload a file to the GCS bucket."""
    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            temp_file.write(file_data.getvalue())
            temp_file.flush()
            
            # Upload using gsutil
            result = subprocess.run(
                ["gsutil", "cp", temp_file.name, f"{BUCKET_URL}/{filename}"],
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
            
            # Clean up temp file
            os.unlink(temp_file.name)
            return True
    except subprocess.CalledProcessError as e:
        st.error(f"Error uploading file: {e.stderr}")
        return False
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return False

def delete_from_bucket(filenames):
    """Delete files from the GCS bucket."""
    try:
        env = os.environ.copy()
        env["CLOUDSDK_PYTHON"] = "python3.11"
        
        for filename in filenames:
            subprocess.run(
                ["gsutil", "rm", f"{BUCKET_URL}/{filename}"],
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Error deleting files: {e.stderr}")
        return False
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return False

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
                # Parse date/time from filename
                # Example: backup_2025-05-22_16-09-32_UTC_local.tar.gz
                m = re.match(r"backup_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_UTC_([^.]+)\.tar\.gz", filename)
                if m:
                    date_str, time_str, environment = m.groups()
                    # Parse UTC timestamp
                    utc_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H-%M-%S")
                    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                    # Convert to local timezone for display
                    local_dt = utc_dt.astimezone()
                    display_date = local_dt.strftime("%b %d, %Y %H:%M:%S %Z")
                    # Validate environment
                    if environment not in ['cloud', 'local']:
                        environment = 'unknown'
                else:
                    utc_dt = None
                    display_date = filename
                    environment = "unknown"
                backup_info.append({
                    'url': gcs_url,
                    'filename': filename,
                    'datetime': utc_dt,
                    'display_date': display_date,
                    'environment': environment,
                    'size': f"{size/1024/1024:.2f} MB" if size else "unknown"
                })
            except Exception:
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

st.title("Admin Dashboard")

# Create tabs for different admin functions
tab1, tab2, tab3 = st.tabs(["User Management", "Data Upload", "Backup Management"])

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
                st.write(f"[DEBUG] CONFIG FILE PATH: {config_path}")
                st.write(f"[DEBUG] Current working directory: {os.getcwd()}")
                st.write(f"[DEBUG] Config exists: {os.path.exists(config_path)}")
                st.write(f"[DEBUG] Config writable: {os.access(config_path, os.W_OK)}")
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
        else:
            st.error("Please fill in all fields")

    # Add new user
    st.subheader("Add New User")
    new_username = st.text_input("Username")
    new_name = st.text_input("Name")
    new_email = st.text_input("Email")
    new_password = st.text_input("Password", type="password")
    is_admin = st.checkbox("Admin privileges")
    
    if st.button("Add User"):
        if new_username and new_name and new_email and new_password:
            if new_username in config['credentials']['usernames']:
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
                st.write(f"[DEBUG] CONFIG FILE PATH: {config_path}")
                st.write(f"[DEBUG] Current working directory: {os.getcwd()}")
                st.write(f"[DEBUG] Config exists: {os.path.exists(config_path)}")
                st.write(f"[DEBUG] Config writable: {os.access(config_path, os.W_OK)}")
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
        else:
            st.error("Please fill in all fields")

with tab2:
    st.header("Data Upload")
    
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
            success_count = 0
            error_count = 0
            skipped_count = 0
            total_files = len(uploaded_files)
            
            # Use the cached GCS file list for checking existence during upload
            # Ensure it's fresh or re-fetch if absolutely necessary (though top-level cache logic should handle it)
            if st.session_state.gcs_bucket_files is None:
                 with st.spinner("Final check on GCS files before upload..."):
                    st.session_state.gcs_bucket_files = list_bucket_files()
                    st.session_state.gcs_files_last_refreshed = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
            
            current_gcs_files_for_upload = st.session_state.gcs_bucket_files if st.session_state.gcs_bucket_files is not None else []
            existing_names_for_upload = [f['name'] for f in current_gcs_files_for_upload]
            
            # Determine conflict action
            current_conflict_action = "Skip existing files" # Default, or retrieve from session_state if set
            if has_conflicts: # has_conflicts should also be determined before this block or stored
                 # This assumes 'conflict_action' is available from the previous run's st.radio
                 # A robust way: store conflict_action in st.session_state if it's chosen
                 # For this example, we'll rely on it being re-evaluated or we use a default.
                 # To make st.radio's value persist, give it a key and read from st.session_state[key]
                 if 'conflict_action_choice' in st.session_state:
                     current_conflict_action = st.session_state.conflict_action_choice
                 else:
                     # If not in session state, it implies the radio button might not have been rendered
                     # or its state needs to be explicitly captured.
                     # This part of the logic might need adjustment based on how `conflict_action` is determined.
                     # For now, we assume `conflict_action` was available from the UI before this button was pressed.
                     # If `has_conflicts` is true, `conflict_action` should have been determined.
                     # This part is tricky with reruns. Let's assume `conflict_action` is somehow available.
                     # To be safe, let's ensure `conflict_action` is defined if `has_conflicts` is true.
                     # This could be done by retrieving it from st.session_state if it was stored there.
                     # For this edit, we'll assume `conflict_action` is accessible.
                     pass

            progress_placeholder = st.empty()

            for i, file in enumerate(uploaded_files):
                progress_placeholder.info(f"Processing file {i+1} of {total_files}: {file.name}...")
                
                if file.name in existing_names_for_upload:
                    # Need to access conflict_action here. Assuming it's available or passed.
                    # If `conflict_action` was from an st.radio, its state must be managed across reruns,
                    # typically by using a key and accessing st.session_state.
                    # For this example, we'll assume `conflict_action` is defined in the scope.
                    # To make this robust, if `has_conflicts` is true, the choice from `st.radio`
                    # (with a key) should be read from `st.session_state`.

                    effective_conflict_action = "Skip existing files" # Default
                    if has_conflicts: # Check if conflict handling is relevant
                        # If `conflict_action` was defined by `st.radio` with a key, retrieve it here.
                        # Example: if st.radio(..., key="my_conflict_action"), then:
                        # effective_conflict_action = st.session_state.my_conflict_action
                        # For this implementation, we need to ensure `conflict_action` is available.
                        # Let's assume `conflict_action` (the variable) is still in scope and holds the user's choice.
                        # This is a potential point of failure if `conflict_action` is not properly managed.
                        # If the original `conflict_action` variable is not available, we must define it.
                        # One way is to get it from session state if the radio button had a key.
                        # Let's assume the `conflict_action` variable is defined in the broader scope.
                        # This part of the code is executed after a rerun, so local variables from before the rerun are lost
                        # unless stored in session_state.

                        # Let's assume `conflict_action` is available. This is a simplification.
                        # For robustness, store the radio button's choice in st.session_state.
                        # e.g., conflict_action = st.radio(..., key="conflict_choice")
                        # then here: chosen_action = st.session_state.get("conflict_choice", "Skip existing files")
                        chosen_action = st.session_state.get("conflict_radio_choice", "Skip existing files") # Fallback

                        if file.name in existing_names_for_upload and chosen_action == "Skip existing files":
                            skipped_count += 1
                            progress_placeholder.info(f"File {i+1} of {total_files}: {file.name} skipped (already exists).")
                            time.sleep(0.5) # Brief pause for readability
                            continue
                
                if upload_to_bucket(file, file.name):
                    success_count += 1
                    progress_placeholder.success(f"File {i+1} of {total_files}: {file.name} uploaded successfully!")
                else:
                    error_count += 1
                    progress_placeholder.error(f"File {i+1} of {total_files}: {file.name} failed to upload.")
                time.sleep(0.5) # Brief pause for readability
            
            progress_placeholder.empty() # Clear the last progress message
            
            # Show detailed results
            if success_count > 0:
                st.success(f"Successfully uploaded {success_count} file(s)")
            if error_count > 0:
                st.error(f"Failed to upload {error_count} file(s)")
            if skipped_count > 0:
                st.info(f"Skipped {skipped_count} existing file(s)")
            
            if success_count > 0 or error_count > 0 or skipped_count > 0:
                st.session_state['uploader_key'] += 1
            
            st.session_state.upload_in_progress = False # Reset the flag
            st.session_state.gcs_bucket_files = None # Invalidate GCS file cache
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
    if st.session_state.get('import_button_pressed'):
        files_to_import = st.session_state.files_for_action
        options = st.session_state.import_options
        override_db = options.get('override_db', False)
        reset_db = options.get('reset_db', False)
        perform_dry_run = options.get('perform_dry_run', False)

        if not files_to_import:
            st.warning("No files were selected for import.")
        else:
            st.info("Import process started...")
            total_files_to_process = len(files_to_import)
            progress_bar = st.progress(0)
            status_text = st.empty()

            total_stats = {
                'filename': 'Multiple Files', 
                'sheets': {'processed': 0, 'total': 0},
                'rows': {'scanned': 0, 'merged': 0, 'errors': 0},
                'actual': {'inserted': 0, 'replaced': 0, 'ignored': 0},
                'unprocessed_sheets_details': [] # New key to store details of unprocessed sheets
            }
            
            try:
                if not perform_dry_run and os.path.exists(os.path.join("data", "podcasts.db")):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = os.path.join(backups_dir, f"podcasts_{timestamp}.db")
                    shutil.copy2(os.path.join("data", "podcasts.db"), backup_path)
                    st.info(f"Created backup of current database: {backup_path}")
                
                if reset_db and not perform_dry_run:
                    db_path = os.path.join("data", "podcasts.db")
                    if os.path.exists(db_path):
                        os.remove(db_path)
                        st.info("Database has been reset before import.")
                
                for idx, filename in enumerate(files_to_import):
                    status_text.text(f"Processing file {idx + 1}/{total_files_to_process}: {filename}...")
                    temp_file = download_from_bucket(filename)
                    if temp_file:
                        try:
                            file_exists = os.path.exists(temp_file)
                            file_size = os.path.getsize(temp_file) if file_exists else 0
                            if file_exists and file_size > 0:
                                stats = import_data(
                                    filepath=temp_file,
                                    override=override_db,
                                    dry_run=perform_dry_run,
                                    reset_db=False, 
                                    skip_backup=True,
                                    original_filename=filename
                                )
                                # st.write("DEBUG: Stats object from import_data for file:", filename, stats) # Temporary debug line - will be removed
                                if stats:
                                    accumulate_stats(total_stats, stats)
                                    with st.expander(f"Details for {filename}", expanded=False):
                                        display_import_summary(stats, override_db, reset_db, perform_dry_run, is_final_summary=False, current_filename_for_display=filename)
                                else:
                                    st.error(f"Failed to get import statistics for {filename}.")
                            else:
                                st.error(f"File {filename} does not exist or is empty after download.")
                        except Exception as e:
                            st.error(f"Error processing {filename}: {e}")
                        finally:
                            if os.path.exists(temp_file):
                                os.unlink(temp_file)
                    else:
                        st.error(f"Failed to download {filename} from GCS.")
                    progress_bar.progress((idx + 1) / total_files_to_process)
                
                status_text.text("Import process completed!")
                st.success("All selected files processed.")
                display_import_summary(total_stats, override_db, reset_db, perform_dry_run, is_final_summary=True)
                
                if not perform_dry_run:
                    st.info("Creating backup of updated data...")
                    if backup_manager.run_backup():
                        st.success("Backup completed successfully")
                        st.session_state.backup_list = list_gcs_backups()
                    else:
                        st.warning("Backup failed, but data import was successful")
            except Exception as e:
                st.error(f"An error occurred during the import process: {e}")
            finally:
                progress_bar.empty()
                status_text.empty()
        
        st.session_state.import_button_pressed = False
        st.session_state.files_for_action = []
        st.session_state.import_options = {}

    if st.session_state.get('delete_button_pressed'):
        files_to_delete = st.session_state.files_for_action
        
        if not files_to_delete:
            st.warning("No files were selected for deletion.")
        else:
            st.info(f"Deletion process started for {len(files_to_delete)} file(s)...")
            success_count = 0
            error_count = 0
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            env = os.environ.copy()
            env["CLOUDSDK_PYTHON"] = "python3.11"

            for idx, filename_to_delete in enumerate(files_to_delete):
                status_text.text(f"Deleting file {idx + 1}/{len(files_to_delete)}: {filename_to_delete}...")
                full_gcs_path = f"{BUCKET_URL}/{filename_to_delete}"
                try:
                    result = subprocess.run(
                        ["gsutil", "rm", full_gcs_path],
                        capture_output=True,
                        text=True,
                        check=True,
                        env=env
                    )
                    success_count += 1
                except subprocess.CalledProcessError as e:
                    st.error(f"Error deleting {filename_to_delete}: {e.stderr}")
                    error_count += 1
                except Exception as e:
                    st.error(f"Unexpected error deleting {filename_to_delete}: {str(e)}")
                    error_count += 1
                finally:
                    progress_bar.progress((idx + 1) / len(files_to_delete))
            
            progress_bar.empty()
            status_text.empty()

            if success_count > 0:
                st.success(f"Successfully deleted {success_count} file(s).")
            if error_count > 0:
                st.error(f"Failed to delete {error_count} file(s).")
            
            if success_count > 0 or error_count > 0:
                st.session_state.gcs_bucket_files = None 
                st.session_state.gcs_files_last_refreshed = None
                # Reset state BEFORE rerun
                st.session_state.delete_button_pressed = False
                st.session_state.files_for_action = []
                st.rerun() 
        
        # Reset state here as well, in case no rerun happened (e.g., no files to delete initially)
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
            else:
                st.error("Manual backup failed")
    
    # List backups
    backups = st.session_state.backup_list

    # Create a DataFrame for better display
    backup_df = pd.DataFrame(backups)
    # Ensure the DataFrame maintains the sorted order
    backup_df = backup_df[['display_date', 'environment', 'size']]
    backup_df.columns = ['Date & Time', 'Environment', 'Size']
    # Add a checkbox column on the left
    backup_df.insert(0, 'Select', False)
    
    st.write(f"Found {len(backups)} backups:")
    
    # Display backups in a table with checkboxes
    edited_df = st.data_editor(
        backup_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Select": st.column_config.CheckboxColumn(
                "Select",
                help="Select backups to act on",
                default=False,
            ),
            "Date & Time": st.column_config.TextColumn(
                "Date & Time",
                width="medium",
            ),
            "Environment": st.column_config.TextColumn(
                "Environment",
                width="small",
            ),
            "Size": st.column_config.TextColumn(
                "Size",
                width="small",
            ),
        },
        disabled=["Date & Time", "Environment", "Size"],
    )
    
    # Get selected backups
    selected_backups = [backups[i] for i, selected in enumerate(edited_df['Select']) if selected]
    
    # --- EXAMINE PANEL ---
    st.markdown("---")
    st.subheader("Examine Backup")
    if len(selected_backups) == 1:
        if st.button("Examine Selected Backup", key="examine_selected_backup"):
            import tempfile, sqlite3, tarfile
            import pathlib
            st.info(f"Examining backup: {selected_backups[0]['filename']}")
            try:
                env = os.environ.copy()
                env["CLOUDSDK_PYTHON"] = "python3.11"
                with tempfile.TemporaryDirectory() as tmpdir:
                    temp_file = os.path.join(tmpdir, "selected_backup.tar.gz")
                    subprocess.run([
                        "gsutil", "cp", selected_backups[0]['url'], temp_file
                    ], check=True, env=env)
                    # Extract all files
                    with tarfile.open(temp_file, "r:gz") as tar:
                        tar.extractall(path=tmpdir)
                    
                    # Check for config file
                    config_found = False
                    config_path = None
                    for root, dirs, files in os.walk(tmpdir):
                        if "config.yaml" in files:
                            config_path = os.path.join(root, "config.yaml")
                            config_found = True
                            break
                    
                    if config_found:
                        st.success("✅ Config file found in backup")
                        # Read and display config contents
                        with open(config_path, 'r') as f:
                            config_content = yaml.safe_load(f)
                            st.write("### Config File Contents")
                            st.json(config_content)
                    else:
                        st.error("❌ Config file not found in backup!")
                    
                    # Check for database
                    db_path = None
                    for root, dirs, files in os.walk(tmpdir):
                        if "podcasts.db" in files:
                            db_path = os.path.join(root, "podcasts.db")
                            break
                    
                    if db_path and os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cur = conn.cursor()
                        # Get all table names
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                        tables = [row[0] for row in cur.fetchall()]
                        st.write("### Database Contents")
                        st.write(f"Tables in backup: {tables}")
                        # Show row count for each table
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
            except Exception as e:
                st.warning(f"Could not examine backup: {e}")
    elif len(selected_backups) > 1:
        st.warning("Please select only one backup to examine.")
    else:
        st.info("Select a single backup to examine its database stats.")
    
    # --- DELETE PANEL ---
    st.markdown("---")
    st.subheader("Delete Backups")
    if selected_backups:
        confirm_delete = st.checkbox("I understand this will permanently delete the selected backups.", key="confirm_delete_backups")
        if st.button("Delete Selected Backups", key="delete_selected_backups"):
            if confirm_delete:
                env = os.environ.copy()
                env["CLOUDSDK_PYTHON"] = "python3.11"
                try:
                    for backup in selected_backups:
                        subprocess.run([
                            "gsutil", "rm", backup['url']
                        ], check=True, env=env)
                    st.success(f"Deleted {len(selected_backups)} backup(s) from GCS.")
                    # Refresh backup list after deletion
                    st.session_state.backup_list = list_gcs_backups()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting backups: {str(e)}")
            else:
                st.warning("Please confirm deletion by checking the box above.")
    else:
        st.info("Select one or more backups to delete.")
    
    # --- RESTORE PANEL ---
    st.markdown("---")
    st.subheader("Restore Backup")
    if backups:
        selected_backup = st.selectbox(
            "Select a backup to restore",
            backups,
            format_func=lambda x: f"{x['display_date']} ({x['environment']}, {x['size']})"
        )
        if selected_backup:
            if st.button("Restore Selected Backup", key="restore_selected_backup_cloud"):
                try:
                    with st.spinner("Restoring backup..."):
                        env = os.environ.copy()
                        env["CLOUDSDK_PYTHON"] = "python3.11"
                        
                        # Determine restore directory based on environment
                        if os.path.exists("/app/data"):
                            restore_dir = "/app/data"
                        else:
                            restore_dir = os.path.join(os.getcwd(), "data")
                        
                        # Create temp directory for extraction
                        temp_dir = os.path.join(restore_dir, "temp")
                        os.makedirs(temp_dir, exist_ok=True)
                        
                        temp_file = os.path.join(temp_dir, "selected_backup.tar.gz")
                        subprocess.run(
                            ["gsutil", "cp", selected_backup['url'], temp_file],
                            check=True,
                            env=env
                        )
                        
                        # Extract to temp directory first
                        extract_dir = os.path.join(temp_dir, "extract")
                        os.makedirs(extract_dir, exist_ok=True)
                        
                        subprocess.run(
                            ["tar", "-xzf", temp_file, "-C", extract_dir],
                            check=True
                        )
                        
                        # Move files to the correct location
                        db_found = False
                        config_found = False
                        for root, dirs, files in os.walk(extract_dir):
                            # Restore podcasts.db
                            if "podcasts.db" in files:
                                src_db = os.path.join(root, "podcasts.db")
                                dest_db = os.path.join(restore_dir, "podcasts.db")
                                shutil.move(src_db, dest_db)
                                db_found = True
                            # Restore config.yaml
                            if "config.yaml" in files:
                                # Determine config directory
                                if os.path.exists("/app/config"):
                                    config_dir = "/app/config"
                                else:
                                    config_dir = os.path.join(os.getcwd(), "config")
                                src_config = os.path.join(root, "config.yaml")
                                dest_config = os.path.join(config_dir, "config.yaml")
                                shutil.move(src_config, dest_config)
                                os.chmod(dest_config, 0o600)
                                config_found = True
                        
                        # Clean up temp files
                        shutil.rmtree(temp_dir)
                        
                        if db_found:
                            st.success(f"Successfully restored from backup: {selected_backup['display_date']}")
                            if config_found:
                                st.info("Config file was also restored from backup.")
                                print("[DEBUG] ADMIN: Config restored. Forcing auth reset and page refresh.")
                                # Force a full reset of authentication state
                                st.session_state.auth_initialized = False
                                st.session_state.authenticator = None
                                st.session_state.config = None
                                st.session_state.authentication_status = None
                                st.session_state.name = None
                                st.session_state.username = None
                                
                                # Inform user and stop to allow manual refresh, which is more reliable
                                st.warning("Restore complete. Please REFRESH your browser page to apply changes and log in.")
                                st.stop() # Stop execution to force refresh
                            else:
                                st.warning("Config file was NOT found in the backup archive. Database restored, but login may be affected.")
                                st.info("Please restart the app or redeploy to ensure data consistency.")
                        else:
                            st.error("Restore completed, but podcasts.db was not found in the backup archive.")
                except Exception as e:
                    st.error(f"Error restoring backup: {str(e)}")
    else:
        st.info("No backups found in Cloud Storage yet.") 