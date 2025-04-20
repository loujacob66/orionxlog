import streamlit as st
import subprocess
import os

def render():
    st.subheader("Upload & Import Excel File")

    uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx"])
    override = st.checkbox("Override existing database (--override-db)")
    dry_run = st.checkbox("Dry run (no changes, just preview) (--dry-run)")

    if uploaded_file is not None:
        temp_path = os.path.join("data", "uploaded_temp.xlsx")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"File uploaded to {temp_path}")

        if st.button("Import Now"):
            cmd = ["python", "commands/import_from_excel.py", temp_path]
            if override:
                cmd.append("--override-db")
            if dry_run:
                cmd.append("--dry-run")
            with st.spinner("Running import script..."):
                result = subprocess.run(cmd, capture_output=True, text=True)
                st.code(result.stdout + result.stderr)