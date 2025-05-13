import streamlit as st
# import subprocess # No longer needed
import os
import io # For capturing stdout
import sys # For redirecting stdout
from datetime import datetime # For timestamping

# --- Path Fix ---
# Add the project root to the Python path to allow importing from 'scripts'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --- End Path Fix ---

from scripts.import_data import import_data # Import the core function

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

def render():
    # Removed: st.set_page_config(layout="wide") # This was causing the error when called from Home.py
    st.subheader("Upload & Import Excel File")

    uploaded_file = st.file_uploader("Choose an Excel file (.xlsx, .xls)", type=["xlsx", "xls"])
    override_db = st.checkbox("Override existing database if it exists")
    perform_dry_run = st.checkbox("Perform a dry run (preview only, no actual database changes)")

    # Define the permanent storage directory for uploads
    permanent_upload_dir = os.path.join("data", "uploaded")

    if uploaded_file is not None:
        # Ensure the permanent upload directory exists
        if not os.path.exists(permanent_upload_dir):
            try:
                os.makedirs(permanent_upload_dir)
                st.caption(f"Created directory: {permanent_upload_dir}")
            except OSError as e:
                st.error(f"Could not create directory {permanent_upload_dir} for storing uploads. Error: {e}")
                return # Stop further processing if directory can't be made

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
            return

        if st.button("Start Import Process"):
            st.info("Import process started...")
            output_capture = io.StringIO()
            original_stdout = sys.stdout
            sys.stdout = output_capture

            try:
                with st.spinner("Processing file and importing data..."):
                    # Call the import_data function with the path to the permanently saved file
                    import_data(filepath=saved_filepath, override=override_db, dry_run=perform_dry_run)
                
                sys.stdout = original_stdout # Restore stdout
                script_output = output_capture.getvalue()
                
                st.success("Import process completed!")
                st.subheader("Import Log & Summary:")
                st.text_area("Output", script_output, height=600) # Use text_area for scrollable, raw output

            except Exception as e:
                sys.stdout = original_stdout # Ensure stdout is restored on error
                script_output = output_capture.getvalue()
                st.error(f"An error occurred during the import process: {e}")
                if script_output:
                    st.subheader("Output before error:")
                    st.text_area("Output", script_output, height=300)
            finally:
                sys.stdout = original_stdout # Ensure stdout is restored in all cases
                output_capture.close()
                # No longer removing the file as it's meant to be stored permanently
                # st.caption(f"File {saved_filepath} is stored permanently.") # Optional: inform user again
    else:
        st.markdown("Please upload an Excel file to begin the import process.")

# To make the page runnable (if this is the main page you test with)
if __name__ == "__main__":
    render()