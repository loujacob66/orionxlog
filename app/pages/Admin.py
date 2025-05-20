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
from datetime import datetime
import shutil
# Add project root to sys.path for robust imports
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from app.authentication import get_authenticator
from scripts.import_data import import_data

def display_import_summary(stats, override_db, reset_db, perform_dry_run):
    """Display a summary of the import process"""
    st.subheader("Import Summary:")
    st.markdown(f"**Action Taken:** {get_import_action_summary(override_db, reset_db, perform_dry_run)}")
    st.markdown(f"**Total sheets processed:** {stats['sheets']['processed']} / {stats['sheets']['total']}")
    st.markdown(f"**Total rows scanned:** {stats['rows']['scanned']}")
    st.markdown(f"**Total rows merged:** {stats['rows']['merged']}")
    st.markdown(f"**Total rows with errors:** {stats['rows']['errors']}")
    st.markdown(f"**Dry run:** {perform_dry_run}")
    st.markdown(f"**Total inserted:** {stats['actual']['inserted']}")
    st.markdown(f"**Total replaced:** {stats['actual']['replaced']}")
    st.markdown(f"**Total ignored:** {stats['actual']['ignored']}")

def get_import_action_summary(override_db, reset_db, perform_dry_run):
    """Get a summary of what actions will be taken"""
    if perform_dry_run:
        if reset_db:
            return ("This was a dry run. No changes were made to the database.\nIf this were not a dry run: The entire database would be deleted before import. Only data from this file would remain after import.")
        elif override_db:
            return ("This was a dry run. No changes were made to the database.\nIf this were not a dry run: Rows for the same period (month/year) would be overwritten. All other data would remain unchanged.")
        else:
            return ("This was a dry run. No changes were made to the database.\nIf this were not a dry run: New rows would be added. Existing rows for the same period would be ignored (not overwritten). All other data would remain unchanged.")
    else:
        if reset_db:
            return ("The entire database was deleted before import. Only data from this file remains after import.")
        elif override_db:
            return ("Rows for the same period (month/year) were overwritten. All other data remains unchanged.")
        else:
            return ("New rows were added. Existing rows for the same period were ignored (not overwritten). All other data remains unchanged.")

def accumulate_stats(total_stats, stats):
    """Accumulate statistics from individual imports"""
    total_stats['sheets']['processed'] += stats['sheets']['processed']
    total_stats['sheets']['total'] += stats['sheets']['total']
    total_stats['rows']['scanned'] += stats['rows']['scanned']
    total_stats['rows']['merged'] += stats['rows']['merged']
    total_stats['rows']['errors'] += stats['rows']['errors']
    total_stats['actual']['inserted'] += stats['actual']['inserted']
    total_stats['actual']['replaced'] += stats['actual']['replaced']
    total_stats['actual']['ignored'] += stats['actual']['ignored']

# Authentication
authenticator, config = get_authenticator()

# Always call login to render the form
name, authentication_status, username = authenticator.login(
    fields={'form_name': 'Admin Dashboard Login', 'location': 'main'}
)

if authentication_status == False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()
else:
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
        st.rerun()
    st.sidebar.write(f'Welcome *{name}*')

    st.title("🔧 Admin Dashboard")

    # Create tabs for different admin functions
    tab1, tab2 = st.tabs(["User Management", "Data Upload"])

    with tab1:
        st.header("User Management")
        
        # Display current users
        st.subheader("Current Users")
        users = config['credentials']['usernames']
        for username, user_data in users.items():
            with st.expander(f"User: {username}"):
                st.write(f"Name: {user_data['name']}")
                st.write(f"Email: {user_data['email']}")
                if st.button(f"Delete User: {username}", key=f"delete_{username}"):
                    if username == 'admin':
                        st.error("Cannot delete admin user")
                    else:
                        del config['credentials']['usernames'][username]
                        with open('config.yaml', 'w') as file:
                            yaml.dump(config, file)
                        st.success(f"User {username} deleted successfully")
                        st.rerun()

        # Add new user
        st.subheader("Add New User")
        new_username = st.text_input("Username")
        new_name = st.text_input("Name")
        new_email = st.text_input("Email")
        new_password = st.text_input("Password", type="password")
        
        if st.button("Add User"):
            if new_username and new_name and new_email and new_password:
                if new_username in config['credentials']['usernames']:
                    st.error("Username already exists")
                else:
                    config['credentials']['usernames'][new_username] = {
                        'name': new_name,
                        'email': new_email,
                        'password': new_password
                    }
                    with open('config.yaml', 'w') as file:
                        yaml.dump(config, file)
                    st.success("User added successfully")
                    st.rerun()
            else:
                st.error("Please fill in all fields")

    with tab2:
        st.header("Data Upload")
        
        # Define directories
        permanent_upload_dir = os.path.join("data", "uploaded")
        initial_logs_dir = os.path.join("data", "initial_logs")
        backups_dir = os.path.join("data", "backups")
        
        # Create three columns for the upload options
        col1, col2, col3 = st.columns(3)
        
        with col1:
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

                    except Exception as e:
                        sys.stdout = original_stdout
                        st.error(f"An error occurred during the import process: {e}")
                    finally:
                        sys.stdout = original_stdout
                        output_capture.close()
            else:
                st.info("Please upload one or more Excel files to begin the import process.")

        with col2:
            st.subheader("Process Initial Logs")
            st.markdown("""
            This option will reset the database andprocess all Excel files in the `data/initial_logs` directory.
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
                    if file.endswith(('.xlsx', '.xls')):
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

        with col3:
            st.subheader("Restore from Backup")
            st.markdown("""
            Restore the database from a previous backup. This will replace the current database with the selected backup.
            """)
            
            # List available backups
            if not os.path.exists(backups_dir):
                st.warning("No backups directory found. Backups will be created when importing data.")
            else:
                backup_files = [f for f in os.listdir(backups_dir) if f.endswith('.db')]
                if not backup_files:
                    st.warning("No backup files found in the backups directory.")
                else:
                    # Sort backups by timestamp (newest first)
                    backup_files.sort(reverse=True)
                    
                    # Create a selectbox with backup options
                    selected_backup = st.selectbox(
                        "Select a backup to restore",
                        backup_files,
                        format_func=lambda x: f"{x} ({datetime.fromtimestamp(os.path.getctime(os.path.join(backups_dir, x))).strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    
                    if st.button("Restore Selected Backup"):
                        if selected_backup:
                            try:
                                # Create a backup of the current database if it exists
                                current_db = os.path.join("data", "podcasts.db")
                                if os.path.exists(current_db):
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    current_backup = os.path.join(backups_dir, f"pre_restore_{timestamp}.db")
                                    shutil.copy2(current_db, current_backup)
                                    st.info(f"Created backup of current database: {current_backup}")
                                
                                # Restore the selected backup
                                backup_path = os.path.join(backups_dir, selected_backup)
                                shutil.copy2(backup_path, current_db)
                                st.success(f"Successfully restored database from backup: {selected_backup}")
                                st.info("Please refresh the page to see the restored data.")
                            except Exception as e:
                                st.error(f"Error restoring backup: {e}")
                        else:
                            st.warning("Please select a backup file to restore.") 