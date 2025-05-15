import streamlit as st
# import subprocess # No longer needed
import os
import io # For capturing stdout
import sys # For redirecting stdout
from datetime import datetime # For timestamping
# Add the project root to the Python path to allow importing from 'scripts'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from app.authentication import get_authenticator
from scripts.import_data import import_data # Import the core function

if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Upload Data", page_icon="⬆️")

# --- Authentication ---
authenticator, _ = get_authenticator()
name, authentication_status, username = authenticator.login(
    fields={'form_name': 'Upload Login', 'location': 'main'}
)
if authentication_status == False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()
else:
    if authenticator.logout(button_name='Logout', location='sidebar', key='logout-upload'):
        st.rerun()
    st.sidebar.write(f'Welcome *{name}*')

# --- Column Configuration ---
COLUMNS_TO_DISPLAY = [
    "title", "feature", "code", "eq_full", "full", "partial", "avg_bw", 
    "total_bw", "created_at", "consumed_at", "consumed_year", 
    "consumed_month", "source_file_path", "url"
]

# Define column configurations with widths and formatting
COLUMN_CONFIG = {
    "title": st.column_config.TextColumn("Title", width=800),
    "feature": st.column_config.TextColumn("Feature", width=150),
    "code": st.column_config.TextColumn("Code", width=100),
    "eq_full": st.column_config.NumberColumn("Eq. Full", width=100, format="%d"),
    "full": st.column_config.NumberColumn("Full", width=100, format="%d"),
    "partial": st.column_config.NumberColumn("Partial", width=100, format="%d"),
    "avg_bw": st.column_config.NumberColumn("Avg BW (MB)", width=120, format="%.2f"),
    "total_bw": st.column_config.NumberColumn("Total BW (MB)", width=120, format="%.2f"),
    "created_at": st.column_config.DatetimeColumn("Created At", width=150, format="YYYY-MM-DD"),
    "consumed_at": st.column_config.DatetimeColumn("Consumed At", width=150, format="YYYY-MM-DD"),
    "consumed_year": st.column_config.NumberColumn("Year", width=80, format="%d"),
    "consumed_month": st.column_config.NumberColumn("Month", width=80, format="%d"),
    "source_file_path": st.column_config.TextColumn("Source File", width=200),
    "url": st.column_config.TextColumn("URL", width=400)
}

def get_import_action_summary(override_db, reset_db, perform_dry_run):
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

def render():
    # Removed: st.set_page_config(layout="wide") # This was causing the error when called from Home.py
    st.subheader("Upload & Import Excel File")

    uploaded_files = st.file_uploader("Choose Excel files (.xlsx, .xls)", type=["xlsx", "xls"], accept_multiple_files=True)
    override_db = st.checkbox("Overwrite rows for the same period (safe, default behavior)")
    reset_db = st.checkbox("Reset entire database (dangerous! Deletes all data before import)")
    perform_dry_run = st.checkbox("Perform a dry run (preview only, no actual database changes)")

    # Define the permanent storage directory for uploads
    permanent_upload_dir = os.path.join("data", "uploaded")

    if uploaded_files:
        # Ensure the permanent upload directory exists
        if not os.path.exists(permanent_upload_dir):
            try:
                os.makedirs(permanent_upload_dir)
                st.caption(f"Created directory: {permanent_upload_dir}")
            except OSError as e:
                st.error(f"Could not create directory {permanent_upload_dir} for storing uploads. Error: {e}")
                return # Stop further processing if directory can't be made

        st.markdown(f"**Action Preview:** {get_import_action_summary(override_db, reset_db, perform_dry_run)}")

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
                for idx, uploaded_file in enumerate(uploaded_files):
                    # Generate new filename with appended, more readable timestamp
                    original_filename_full = uploaded_file.name
                    base, ext = os.path.splitext(original_filename_full)
                    # Sanitize base filename (e.g., replace spaces with underscores)
                    safe_base_filename = base.replace(" ", "_").replace("/", "_") # Add other sanitizations if needed
                    
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") # More readable format
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
                        stats = import_data(filepath=saved_filepath, override=override_db, dry_run=perform_dry_run, reset_db=reset_flag)
                        
                        if stats:
                            # Accumulate stats
                            total_stats['sheets']['processed'] += stats['sheets']['processed']
                            total_stats['sheets']['total'] += stats['sheets']['total']
                            total_stats['rows']['scanned'] += stats['rows']['scanned']
                            total_stats['rows']['merged'] += stats['rows']['merged']
                            total_stats['rows']['errors'] += stats['rows']['errors']
                            total_stats['actual']['inserted'] += stats['actual']['inserted']
                            total_stats['actual']['replaced'] += stats['actual']['replaced']
                            total_stats['actual']['ignored'] += stats['actual']['ignored']

                sys.stdout = original_stdout  # Restore stdout
                st.success("Import process completed!")
                st.subheader("Import Summary:")
                st.markdown(f"**Action Taken:** {get_import_action_summary(override_db, reset_db, perform_dry_run)}")
                st.markdown(f"**Total sheets processed:** {total_stats['sheets']['processed']} / {total_stats['sheets']['total']}")
                st.markdown(f"**Total rows scanned:** {total_stats['rows']['scanned']}")
                st.markdown(f"**Total rows merged:** {total_stats['rows']['merged']}")
                st.markdown(f"**Total rows with errors:** {total_stats['rows']['errors']}")
                st.markdown(f"**Dry run:** {perform_dry_run}")
                st.markdown(f"**Total inserted:** {total_stats['actual']['inserted']}")
                st.markdown(f"**Total replaced:** {total_stats['actual']['replaced']}")
                st.markdown(f"**Total ignored:** {total_stats['actual']['ignored']}")

            except Exception as e:
                sys.stdout = original_stdout  # Ensure stdout is restored on error
                st.error(f"An error occurred during the import process: {e}")
            finally:
                sys.stdout = original_stdout  # Ensure stdout is restored in all cases
                output_capture.close()
    else:
        st.markdown("Please upload one or more Excel files to begin the import process.")

# To make the page runnable (if this is the main page you test with)
if __name__ == "__main__":
    render()