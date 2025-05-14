import streamlit as st
st.set_page_config(layout="wide", page_title="Explore Data", page_icon="🔍")
import pandas as pd
import os # Required for path operations if we were to build path here
import sys # Required for sys.path manipulation
# Ensure app.utils can be imported
# Assuming Explore.py is in app/pages/, then ../.. is project root
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from app.authentication import get_authenticator
from app.utils import load_db # Import load_db

# --- Authentication ---
authenticator, _ = get_authenticator()
name, authentication_status, username = authenticator.login(
    fields={'form_name': 'Explore Login', 'location': 'main'}
)
if authentication_status == False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()
else:
    if authenticator.logout(button_name='Logout', location='sidebar', key='logout-explore'):
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
    "title": st.column_config.TextColumn("Title", width=300),
    "feature": st.column_config.TextColumn("Feature", width=100),
    "code": st.column_config.TextColumn("Code", width=50),
    "eq_full": st.column_config.NumberColumn("Eq. Full", width=60, format="%d"),
    "full": st.column_config.NumberColumn("Full", width=75, format="%d"),
    "partial": st.column_config.NumberColumn("Partial", width=75, format="%d"),
    "avg_bw": st.column_config.NumberColumn("Avg BW (MB)", width=90, format="%.2f"),
    "total_bw": st.column_config.NumberColumn("Total BW (MB)", width=90, format="%.2f"),
    "created_at": st.column_config.DatetimeColumn("Created At", width=100, format="YYYY-MM-DD"),
    "consumed_at": st.column_config.DatetimeColumn("Consumed At", width=100, format="YYYY-MM-DD"),
    "consumed_year": st.column_config.NumberColumn("Year", width=60, format="%d"),
    "consumed_month": st.column_config.NumberColumn("Month", width=90, format="%d"),
    "source_file_path": st.column_config.TextColumn("Source File", width=200),
    "url": st.column_config.TextColumn("URL", width=400)
}

# Placeholder for data loading logic, to be refined.
# Ideally, this would use the load_db from Home.py or a shared utility.
def load_data_for_explore():
    # This is a simplified version. We'll need to ensure this function
    # is robust, like the load_db in Home.py.
    # For now, let's assume it can return an empty DataFrame if data isn't found.
    # We'll need to import os and sqlite3 if we replicate Home.py's load_db here.
    # Or, better, refactor load_db to be importable.
    # For now, returning an empty DataFrame to avoid NameError on load_db
    print("Explore.py: load_data_for_explore called. DATA LOADING NEEDS TO BE IMPLEMENTED HERE.")
    # This part needs to be properly implemented, e.g., by importing and using load_db from Home or a util file.
    # For now, to make the script runnable without Home.py's load_db, return empty.
    # We can copy the load_db logic here, or make it importable.
    # Let's assume we will make it importable later and for now, for it to run, return empty.
    # This is a TEMPORARY placeholder to avoid errors during this step.
    # Real implementation will call the actual data loading.
    return pd.DataFrame() 

def render(df=None):
    st.subheader("Explore Podcast Downloads Data")

    if df is None:
        # If no DataFrame is passed, try to load it directly.
        # This happens when Explore.py is run as a standalone page.
        df = load_db() # Use the imported load_db function

    if df.empty:
        st.warning("No data available to explore. Please upload data first.")
        return

    # Start with a definite copy of the DataFrame to avoid SettingWithCopyWarning downstream
    df_filtered = df.copy()

    with st.sidebar:
        st.markdown("### Filters")

        # Feature Filter (now appears first)
        if "feature" in df_filtered.columns and not df_filtered["feature"].dropna().empty:
            features = sorted(df_filtered["feature"].dropna().unique().tolist())
            selected_features = st.multiselect("Feature", features, default=features)
            if selected_features:
                 df_filtered = df_filtered[df_filtered["feature"].isin(selected_features)]
        else:
            st.caption("No 'feature' data to filter.")

        # Year Filter (using consumed_year) - BASED ON FULL DATA
        if "consumed_year" in df.columns:
            years = sorted(df["consumed_year"].dropna().unique().tolist())
            if years:
                selected_years = st.multiselect("Consumption Year", years, default=years)
                df_filtered = df_filtered[df_filtered["consumed_year"].isin(selected_years)]
            else:
                st.caption("No valid years found in the data.")
        else:
            st.caption("No 'consumed_year' column found in the data.")
        
    st.markdown("### Filtered Data View")
    
    # Get only the columns that exist in the DataFrame
    existing_display_columns = [col for col in COLUMNS_TO_DISPLAY if col in df_filtered.columns]

    # Add month_display column with '~' if assumed_month is true
    if 'consumed_month' in df_filtered.columns and 'assumed_month' in df_filtered.columns:
        df_filtered = df_filtered.copy()
        df_filtered['month_display'] = df_filtered['consumed_month'].astype(str)
        df_filtered.loc[df_filtered['assumed_month'] == 1, 'month_display'] = df_filtered['consumed_month'].astype(str) + '~'
        # Replace consumed_month with month_display for display
        if 'month_display' not in existing_display_columns:
            existing_display_columns = [col if col != 'consumed_month' else 'month_display' for col in existing_display_columns]

    if not df_filtered.empty and existing_display_columns:
        df_to_show = df_filtered[existing_display_columns]
        # Create active column config with only the columns that exist
        active_column_config = {k: v for k, v in COLUMN_CONFIG.items() if k in df_to_show.columns}
        # Add config for month_display
        if 'month_display' in df_to_show.columns:
            active_column_config['month_display'] = st.column_config.TextColumn("Month", width=80)
        st.dataframe(
            df_to_show,
            column_config=active_column_config,
            use_container_width=True,
            hide_index=True
        )
        st.caption('~ = Month assumed from yearly data')
    elif df_filtered.empty:
        st.info("No data matches the current filter criteria.")
    else:
        st.warning("Could not display data. Required columns might be missing or data is empty after filtering.")

# Call render when the page is accessed directly.
# Home.py will call render(df) for its tab.
# Remove the if __name__ == "__main__": block at the bottom
# Home.py will call render(df) for its tab. 

render() 