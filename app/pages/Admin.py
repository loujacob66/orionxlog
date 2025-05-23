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
from datetime import datetime, timezone
import shutil
import subprocess
import pandas as pd
import time
import re

# Define directory paths
initial_logs_dir = os.path.join("data", "initial_logs")
backups_dir = os.path.join("data", "backups")
permanent_upload_dir = os.path.join("data", "uploaded")

# Helper function to accumulate import statistics
def accumulate_stats(total_stats, new_stats):
    """Accumulate statistics from multiple import operations."""
    for category in total_stats:
        for stat in total_stats[category]:
            if stat in new_stats.get(category, {}):
                total_stats[category][stat] += new_stats[category][stat]

def display_import_summary(stats, override_db, reset_db, dry_run):
    """Display a summary of the import operation."""
    st.write("\n")
    st.write("=" * 70)
    st.write(f" Import Summary for: {stats.get('filename', 'Unknown file')}")
    st.write("=" * 70)
    
    # File type and mode
    st.write(f"File Type: {stats.get('file_type', 'Unknown')}")
    st.write(f"Processing Mode: {'Dry Run' if dry_run else 'Actual Import'}")
    st.write(f"Source Path: {stats.get('source_path', 'Unknown')}")
    st.write("\n")
    
    # File & Sheet Details
    st.write("File & Sheet Details:")
    st.write(f"  Sheets in file: {stats.get('sheets', {}).get('total', 0)}")
    st.write(f"  Sheets targeted: {stats.get('sheets', {}).get('targeted', 0)}")
    st.write(f"  Sheets processed: {stats.get('sheets', {}).get('processed', 0)}")
    
    # Skipped sheets
    skipped = stats.get('sheets', {}).get('skipped', {})
    if skipped:
        st.write("  Sheets skipped:")
        for reason, count in skipped.items():
            st.write(f"    - {reason}: {count}")
    
    st.write("\n")
    
    # Row Processing
    st.write("Row Processing:")
    st.write(f"  Total rows scanned: {stats.get('rows', {}).get('scanned', 0)}")
    st.write(f"  Rows merged: {stats.get('rows', {}).get('merged', 0)}")
    st.write(f"  Processing errors: {stats.get('rows', {}).get('errors', 0)}")
    
    st.write("\n")
    
    # Database Changes
    st.write("Database Changes (Actual):")
    st.write(f"  Inserted: {stats.get('actual', {}).get('inserted', 0)}")
    st.write(f"  Replaced: {stats.get('actual', {}).get('replaced', 0)}")
    st.write(f"  Ignored: {stats.get('actual', {}).get('ignored', 0)}")
    
    st.write("-" * 70)

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
                                    'password': new_password,
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
                    'password': new_password,
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
                                    'password': new_password,
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
    st.subheader("Upload New Files")
    uploaded_files = st.file_uploader("Choose Excel files (.xlsx, .xls)", type=["xlsx", "xls"], accept_multiple_files=True)
    if uploaded_files:
        st.markdown("### Import Options")
        override_db = st.checkbox("Update existing data for the same month/year (recommended)")
        reset_db = st.checkbox("Clear all existing data before import (use with caution)")
        perform_dry_run = st.checkbox("Preview changes without saving (no data will be modified)")
        if st.button("Start Import Process"):
            st.info("Import process started...")
            output_capture = io.StringIO()
            original_stdout = sys.stdout
            sys.stdout = output_capture
            total_stats = {
                'sheets': {'processed': 0, 'total': 0},
                'rows': {'scanned': 0, 'merged': 0, 'errors': 0},
                'actual': {'inserted': 0, 'replaced': 0, 'ignored': 0}
            }
            try:
                # Create a single backup before starting if we're not doing a dry run
                if not perform_dry_run and os.path.exists(os.path.join("data", "podcasts.db")):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = os.path.join(backups_dir, f"podcasts_{timestamp}.db")
                    shutil.copy2(os.path.join("data", "podcasts.db"), backup_path)
                    st.info(f"Created backup of current database: {backup_path}")
                for idx, uploaded_file in enumerate(uploaded_files):
                    # Generate new filename with appended, more readable timestamp
                    original_filename_full = uploaded_file.name
                    base, ext = os.path.splitext(original_filename_full)
                    safe_base_filename = base.replace(" ", "_").replace("/", "_")
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    new_filename = f"{safe_base_filename}_{timestamp}{ext}"
                    saved_filepath = os.path.join(permanent_upload_dir, new_filename)
                    # Save the uploaded file to the permanent location
                    try:
                        with open(saved_filepath, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        st.info(f"File saved as: {saved_filepath}")
                    except IOError as e:
                        st.error(f"Failed to save uploaded file to {saved_filepath}. Error: {e}")
                        continue
                    with st.spinner(f"Processing file {uploaded_file.name}..."):
                        # Only reset DB for the first file
                        reset_flag = reset_db if idx == 0 else False
                        stats = import_data(
                            filepath=saved_filepath,
                            override=override_db,
                            dry_run=perform_dry_run,
                            reset_db=reset_flag,
                            skip_backup=True  # Skip backup since we created it at the start
                        )
                        if stats:
                            accumulate_stats(total_stats, stats)
                sys.stdout = original_stdout
                st.success("Import process completed!")
                display_import_summary(total_stats, override_db, reset_db, perform_dry_run)
                # Trigger backup after successful import
                if not perform_dry_run:
                    st.info("Creating backup of updated data...")
                    if backup_manager.run_backup():
                        st.success("Backup completed successfully")
                    else:
                        st.warning("Backup failed, but data import was successful")
            except Exception as e:
                sys.stdout = original_stdout
                st.error(f"An error occurred during the import process: {e}")
            finally:
                sys.stdout = original_stdout
                output_capture.close()
    else:
        st.info("Please upload one or more Excel files to begin the import process.")
    st.markdown("---")
    st.subheader("Process Initial Logs")
    st.markdown("""
    This option will reset the database and process all Excel files in the `data/initial_logs` directory.\
    Monthly files will be processed first, followed by the multi-tabbed report file with annual historical data.
    """)
    if st.button("Process Initial Logs"):
        st.info("Processing initial logs from data/initial_logs directory...")
        if not os.path.exists(initial_logs_dir):
            st.error(f"Initial logs directory not found at {initial_logs_dir}")
            st.stop()
        # Get all files from initial_logs directory
        initial_files = []
        for file in os.listdir(initial_logs_dir):
            if file.endswith((".xlsx", ".xls")):
                file_path = os.path.join(initial_logs_dir, file)
                initial_files.append(file_path)
        if not initial_files:
            st.warning("No Excel files found in initial_logs directory")
            st.stop()
        # Sort files to ensure monthly data is processed before report
        monthly_files = [f for f in initial_files if not os.path.basename(f).startswith('report0416')]
        report_file = [f for f in initial_files if os.path.basename(f).startswith('report0416')]
        total_stats = {
            'sheets': {'processed': 0, 'total': 0},
            'rows': {'scanned': 0, 'merged': 0, 'errors': 0},
            'actual': {'inserted': 0, 'replaced': 0, 'ignored': 0}
        }
        # Process monthly files first
        if monthly_files:
            st.subheader("Processing Monthly Files")
            # Create a single backup before starting the process
            current_db = os.path.join("data", "podcasts.db")
            if os.path.exists(current_db):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(backups_dir, f"podcasts_{timestamp}.db")
                shutil.copy2(current_db, backup_path)
                st.info(f"Created backup of current database: {backup_path}")
            for file_path in monthly_files:
                st.info(f"Processing {os.path.basename(file_path)}...")
                stats = import_data(
                    filepath=file_path,
                    override=True,  # Always override for initial logs
                    dry_run=False,  # Never dry run for initial logs
                    reset_db=True if file_path == monthly_files[0] else False,  # Reset only for first file
                    skip_backup=True  # Skip backup since we created it at the start
                )
                if stats:
                    accumulate_stats(total_stats, stats)
                    display_import_summary(stats, True, file_path == monthly_files[0], False)
        # Process report file last
        if report_file:
            st.subheader("Processing Report File")
            for file_path in report_file:
                st.info(f"Processing {os.path.basename(file_path)}...")
                stats = import_data(
                    filepath=file_path,
                    override=True,  # Always override for initial logs
                    dry_run=False,  # Never dry run for initial logs
                    reset_db=False,  # Never reset DB for report file
                    skip_backup=True  # Skip backup since we created it at the start
                )
                if stats:
                    accumulate_stats(total_stats, stats)
                    display_import_summary(stats, True, False, False)
        st.success("Initial logs processing completed!")
        display_import_summary(total_stats, True, True, False)

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
                            else:
                                st.warning("Config file was NOT found in the backup archive.")
                            st.info("**Please restart the app or redeploy the service to ensure the restored data is loaded.**")
                        else:
                            st.error("Restore completed, but podcasts.db was not found in the backup archive.")
                except Exception as e:
                    st.error(f"Error restoring backup: {str(e)}")
    else:
        st.info("No backups found in Cloud Storage yet.") 