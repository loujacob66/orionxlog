import streamlit as st
st.set_page_config(layout="wide", page_title="OrionX Podcast Trends", page_icon="📊")

# Add CSS to hide sidebar initially
st.markdown("""
    <style>
        section[data-testid="stSidebar"] {
            display: none;
        }
    </style>
""", unsafe_allow_html=True)

import pandas as pd
import sqlite3
import os
import sys
# Add project root to sys.path for robust imports
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from authentication import get_authenticator, display_user_management
from app.utils import load_db 
from app.Upload import render

# --- Column Configuration ---
COLUMNS_TO_DISPLAY = [
    "title", "feature", "code", "eq_full", "full", "partial", "avg_bw", 
    "total_bw", "created_at", "consumed_month", "consumed_year", 
    "source_file_path", "url"
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
    "consumed_at": st.column_config.DatetimeColumn("Viewed At", width=1050, format="YYYY-MM-DD"),
    "consumed_year": st.column_config.NumberColumn("Viewed Year", width=60, format="%d"),
    "consumed_month": st.column_config.NumberColumn("Viewed Month", width=90, format="%d"),
    "source_file_path": st.column_config.TextColumn("Source File", width=200),
    "url": st.column_config.TextColumn("URL", width=400)
}

# Authentication
authenticator, _ = get_authenticator()

# Always call login to render the form
name, authentication_status, username = authenticator.login(
    fields={'form_name': 'OrionX Podcast Trends Login', 'location': 'main'}
)

if authentication_status == False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()
else:
    # Show the sidebar after successful authentication
    st.markdown("""
        <style>
            section[data-testid="stSidebar"] {
                display: block;
            }
        </style>
    """, unsafe_allow_html=True)
    
    # User is authenticated
    if authenticator.logout(button_name='Logout', location='sidebar', key='logout-main'):
        st.rerun()
    st.sidebar.write(f'Welcome *{name}*')

    # --- CHECK FOR USER MANAGEMENT FLAG HERE ---
    if st.session_state.get('show_user_management'):
        display_user_management()
        del st.session_state['show_user_management']
        st.stop()

    # Add user management page for admin
    if username == 'admin':
        st.sidebar.markdown("---")
        if st.sidebar.button("User Management"):
            display_user_management()
            st.stop()  # Stop further execution

    st.title("📊 OrionX Podcast Trends")
    df = load_db()

    # Ensure rowid is a column if it's the index, for consistent column ordering later
    if 'rowid' not in df.columns and ('index' == df.index.name or df.index.name is None):
        df_display = df.reset_index()
        if 'index' in df_display.columns: # if previous index was unnamed, it might be 'index'
            df_display = df_display.rename(columns={'index': 'rowid'})
        elif 'level_0' in df_display.columns: # another possible default name for reset index
            df_display = df_display.rename(columns={'level_0': 'rowid'})
        # If it was already named rowid by reset_index(), no change needed here.
    else:
        df_display = df.copy()

    # --- Tabs ---
    tab1, tab2, tab3 = st.tabs(["Explore Data", "Raw Table View", "Upload Data"])

    with tab1:
        # --- Main Table (match Analytics.py) with Filters ---
        if not df.empty:
            df_main = df.copy()
            st.sidebar.header("Filters")
            # Feature Filter (first)
            if 'feature' in df_main.columns and not df_main['feature'].dropna().empty:
                features_available = sorted(df_main['feature'].dropna().unique().tolist())
                selected_features = st.sidebar.multiselect("Feature", features_available, default=features_available)
                if selected_features:
                    df_main = df_main[df_main['feature'].isin(selected_features)]
            else:
                st.sidebar.caption("No 'feature' data for filtering.")
            # Year Filter (second)
            if 'consumed_year' in df_main.columns and not df_main['consumed_year'].dropna().empty:
                min_year_val = df_main['consumed_year'].dropna().min()
                max_year_val = df_main['consumed_year'].dropna().max()
                if pd.notna(min_year_val) and pd.notna(max_year_val):
                    min_year, max_year = int(min_year_val), int(max_year_val)
                    selected_years = st.sidebar.slider(
                        "Viewed Year Range",
                        min_year, max_year,
                        (min_year, max_year)
                    )
                    df_main = df_main[(df_main['consumed_year'] >= selected_years[0]) & (df_main['consumed_year'] <= selected_years[1])]
                else:
                    st.sidebar.caption("Could not determine year range for filtering.")
            else:
                st.sidebar.caption("No 'consumed_year' data for filtering.")
            # Show only the filename for source_file_path
            if 'source_file_path' in df_main.columns:
                df_main['source_file_path'] = df_main['source_file_path'].apply(lambda x: os.path.basename(x) if pd.notna(x) else x)
            # Add month_display column with '~' if assumed_month is true
            if 'consumed_month' in df_main.columns and 'assumed_month' in df_main.columns:
                df_main['month_display'] = df_main['consumed_month'].astype(str)
                df_main.loc[df_main['assumed_month'] == 1, 'month_display'] = df_main['consumed_month'].astype(str) + '~'
                display_columns = [col if col != 'consumed_month' else 'month_display' for col in COLUMNS_TO_DISPLAY if col in df_main.columns]
            else:
                display_columns = [col for col in COLUMNS_TO_DISPLAY if col in df_main.columns]
            # Column config
            active_column_config = {k: v for k, v in COLUMN_CONFIG.items() if k in df_main.columns}
            if 'month_display' in df_main.columns:
                active_column_config['month_display'] = st.column_config.TextColumn("Viewed Month", width=90)
            st.dataframe(
                df_main[display_columns],
                column_config=active_column_config,
                use_container_width=True,
                hide_index=True
            )
            if 'month_display' in df_main.columns:
                st.caption('~ = Month assumed from yearly data')
        else:
            st.warning("No data found. Try uploading an Excel file in the Upload tab.")

    with tab2:
        # --- Raw Table View: just show the full raw data table, no debug info ---
        if not df_display.empty:
            # Show only the filename for source_file_path
            if 'source_file_path' in df_display.columns:
                df_display['source_file_path'] = df_display['source_file_path'].apply(lambda x: os.path.basename(x) if pd.notna(x) else x)
            # Add month_display column with '~' if assumed_month is true
            if 'consumed_month' in df_display.columns and 'assumed_month' in df_display.columns:
                df_display['month_display'] = df_display['consumed_month'].astype(str)
                df_display.loc[df_display['assumed_month'] == 1, 'month_display'] = df_display['consumed_month'].astype(str) + '~'
                display_columns = [col if col != 'consumed_month' else 'month_display' for col in COLUMNS_TO_DISPLAY if col in df_display.columns]
            else:
                display_columns = [col for col in COLUMNS_TO_DISPLAY if col in df_display.columns]
            # Column config
            active_column_config = {k: v for k, v in COLUMN_CONFIG.items() if k in df_display.columns}
            if 'month_display' in df_display.columns:
                active_column_config['month_display'] = st.column_config.TextColumn("Viewed Month", width=90)
            st.dataframe(
                df_display[display_columns],
                column_config=active_column_config,
                use_container_width=True,
                hide_index=True
            )
            if 'month_display' in df_display.columns:
                st.caption('~ = Month assumed from yearly data')
        else:
            st.info("No data to display.")

    with tab3:
        render()
