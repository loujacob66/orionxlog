import streamlit as st
st.set_page_config(layout="wide", page_title="Podcast Analytics", page_icon="📊")
import pandas as pd
import sqlite3
import os
import sys
# Add the project root to the Python path to allow importing from 'app'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
import plotly.express as px
from app.authentication import get_authenticator

# --- Authentication ---
authenticator, _ = get_authenticator()
name, authentication_status, username = authenticator.login(
    fields={'form_name': 'Analytics Login', 'location': 'main'}
)
if authentication_status == False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()
else:
    if authenticator.logout(button_name='Logout', location='sidebar', key='logout-analytics'):
        st.rerun()
    st.sidebar.write(f'Welcome *{name}*')

# --- Path Fix ---
# Add the project root to the Python path to allow importing from 'scripts' if needed by helper functions
# Though for this page, we might not directly import from 'scripts', it's good practice for consistency.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')) # Adjusted for pages subdir
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --- End Path Fix ---

# --- Page Configuration ---
# Page config is set in Home.py or by Streamlit for multipage apps; remove from individual pages if not the main script.

# --- Column Configuration ---
COLUMNS_TO_DISPLAY = [
    "title", "feature", "code", "eq_full", "full", "partial", "avg_bw", 
    "total_bw", "created_at","consumed_month","consumed_year", 
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
    "consumed_at": st.column_config.DatetimeColumn("Viewed At", width=100, format="YYYY-MM-DD"),
    "consumed_year": st.column_config.NumberColumn("Viewed Year", width=60, format="%d"),
    "consumed_month": st.column_config.NumberColumn("Viewed Month", width=90, format="%d"),
    "source_file_path": st.column_config.TextColumn("Source File", width=200),
    "url": st.column_config.TextColumn("URL", width=400)
}

# --- Data Loading and Caching ---
@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_podcast_data():
    # Construct path relative to the project root, now that project_root is correctly defined
    db_path = os.path.join(project_root, "data", "podcasts.db")
    if not os.path.exists(db_path):
        st.error(f"Database not found at {db_path}. Please import data first using the 'Upload' page.")
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM podcasts", conn)
        conn.close()
        
        # Basic Data Preprocessing
        if df.empty:
            return pd.DataFrame()

        df['consumed_at'] = pd.to_datetime(df['consumed_at'], errors='coerce')
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        
        numeric_cols = ['full', 'partial', 'avg_bw', 'total_bw', 'eq_full', 'consumed_year', 'consumed_month']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Ensure eq_full is not NaN for key calculations, default to 0 if it was NaN
        if 'eq_full' in df.columns:
            df['eq_full'] = df['eq_full'].fillna(0)

        return df
    except Exception as e:
        st.error(f"Error loading data from database: {e}")
        return pd.DataFrame()

# --- Main Application ---
def render(): # Changed function name to render for consistency with other pages if loaded by Home.py
    st.title("📊 Podcast Data Analytics")
    st.markdown("Explore trends and insights from your podcast data.")

    df_raw = load_podcast_data()

    if df_raw.empty:
        st.warning("No podcast data loaded. Please upload data via the 'Upload' page.")
        return

    # --- Sidebar Filters ---
    st.sidebar.header("Filters")
    
    # Filtered DataFrame - start with a copy
    df_filtered = df_raw.copy()

    # Feature Filter (now appears first)
    if 'feature' in df_filtered.columns and not df_filtered['feature'].dropna().empty:
        features_available = sorted(df_filtered['feature'].dropna().unique().tolist())
        selected_features = st.sidebar.multiselect("Feature", features_available, default=features_available)
        if selected_features:
            df_filtered = df_filtered[df_filtered['feature'].isin(selected_features)]
    else:
        st.sidebar.caption("No 'feature' data for filtering.")

    # Year Filter
    if 'consumed_year' in df_filtered.columns and not df_filtered['consumed_year'].dropna().empty:
        min_year_val = df_filtered['consumed_year'].dropna().min()
        max_year_val = df_filtered['consumed_year'].dropna().max()
        if pd.notna(min_year_val) and pd.notna(max_year_val):
            min_year, max_year = int(min_year_val), int(max_year_val)
            selected_years = st.sidebar.slider(
                "Consumption Year Range",
                min_year, max_year,
                (min_year, max_year)
            )
            df_filtered = df_filtered[(df_filtered['consumed_year'] >= selected_years[0]) & (df_filtered['consumed_year'] <= selected_years[1])]
        else:
            st.sidebar.caption("Could not determine year range for filtering.")
    else:
        st.sidebar.caption("No 'consumed_year' data for filtering.")

    # Top N Selector for relevant charts
    top_n = st.sidebar.number_input("Number of Top Items to Display (e.g., for Top Podcasts)", min_value=3, max_value=50, value=10, step=1)


    if df_filtered.empty:
        st.warning("No data matches the current filter criteria. Please adjust filters in the sidebar.")
        return

    # --- Tabs for Different Visualizations ---
    tab1, tab2, tab3 = st.tabs([
        "📈 Download Overview & Trends", 
        "🎙️ Individual Podcast Deep Dive", 
        "🔬 Feature & Bandwidth Insights"
    ])

    with tab1:
        st.header("Download Overview & Trends")

        # Chart 1.1: Top N Podcasts (Overall) by eq_full
        if not df_filtered.empty and 'title' in df_filtered.columns and 'eq_full' in df_filtered.columns:
            st.subheader(f"Top {top_n} Podcasts by Equivalent Full Downloads")
            # Ensure 'eq_full' is numeric before sum, handle potential all-NaN case after filtering
            df_filtered.loc[:, 'eq_full'] = pd.to_numeric(df_filtered['eq_full'], errors='coerce').fillna(0)
            top_podcasts_overall = df_filtered.groupby('title')['eq_full'].sum().nlargest(top_n).reset_index()
            if not top_podcasts_overall.empty and top_podcasts_overall['eq_full'].sum() > 0: # Check if there's actual data to plot
                fig_top_overall = px.bar(
                    top_podcasts_overall, 
                    x='eq_full', 
                    y='title', 
                    orientation='h',
                    title=f"Top {top_n} Podcasts (Sum of Eq. Full Downloads)",
                    labels={'eq_full': 'Total Equivalent Full Downloads', 'title': 'Podcast Title'},
                    height=max(400, top_n * 40) # Adjust height based on N
                )
                fig_top_overall.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_top_overall, use_container_width=True)
            else:
                st.info("No podcast data available for 'Top Podcasts' chart with current filters (or all values are zero).")
        else:
            st.info("Required columns ('title', 'eq_full') not available or data is empty for 'Top Podcasts' chart.")

        # Add a data table view with consistent column formatting
        st.subheader("Data Table View")
        # Get only the columns that exist in the DataFrame
        existing_display_columns = [col for col in COLUMNS_TO_DISPLAY if col in df_filtered.columns]

        # Show only the filename for source_file_path
        if 'source_file_path' in df_filtered.columns:
            df_filtered = df_filtered.copy()
            df_filtered['source_file_path'] = df_filtered['source_file_path'].apply(lambda x: os.path.basename(x) if pd.notna(x) else x)

        if existing_display_columns:
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

        # Chart 1.2: Total Downloads Over Time (Monthly)
        if not df_filtered.empty and 'consumed_at' in df_filtered.columns and 'eq_full' in df_filtered.columns:
            st.subheader("Total Downloads Over Time (Monthly)")
            monthly_downloads = df_filtered.copy() # Work with a copy for modifications
            monthly_downloads['consumed_at'] = pd.to_datetime(monthly_downloads['consumed_at'], errors='coerce')
            monthly_downloads.dropna(subset=['consumed_at'], inplace=True) # Remove rows where date conversion failed
            
            if not monthly_downloads.empty:
                monthly_downloads['year_month'] = monthly_downloads['consumed_at'].dt.to_period('M').astype(str)
                monthly_downloads.loc[:, 'eq_full'] = pd.to_numeric(monthly_downloads['eq_full'], errors='coerce').fillna(0)
                monthly_downloads_agg = monthly_downloads.groupby('year_month')['eq_full'].sum().reset_index()
                monthly_downloads_agg = monthly_downloads_agg.sort_values('year_month')

                if not monthly_downloads_agg.empty and monthly_downloads_agg['eq_full'].sum() > 0:
                    fig_monthly_trend = px.line(
                        monthly_downloads_agg,
                        x='year_month',
                        y='eq_full',
                        title="Total Equivalent Full Downloads per Month",
                        labels={'year_month': 'Month', 'eq_full': 'Total Equivalent Full Downloads'},
                        markers=True
                    )
                    fig_monthly_trend.update_xaxes(type='category')
                    st.plotly_chart(fig_monthly_trend, use_container_width=True)
                else:
                    st.info("No data available for 'Total Downloads Over Time' chart with current filters (or all values are zero).")
            else:
                 st.info("No valid 'consumed_at' dates available after filtering for 'Total Downloads Over Time' chart.")
        else:
            st.info("Required columns ('consumed_at', 'eq_full') not available or data is empty for 'Total Downloads Over Time' chart.")

    with tab2:
        st.header("Individual Podcast Deep Dive")
        if not df_filtered.empty and 'title' in df_filtered.columns:
            podcast_titles = sorted(df_filtered['title'].dropna().unique().tolist())
            if podcast_titles:
                selected_podcast_titles = st.multiselect(
                    "Select Podcast(s) for Deep Dive", 
                    podcast_titles, 
                    default=podcast_titles[:min(1, len(podcast_titles))] if podcast_titles else []
                )

                if selected_podcast_titles:
                    df_podcast_dive = df_filtered[df_filtered['title'].isin(selected_podcast_titles)].copy()
                    
                    if not df_podcast_dive.empty and 'consumed_at' in df_podcast_dive.columns and 'eq_full' in df_podcast_dive.columns:
                        st.subheader("Downloads Over Time for Selected Podcast(s)")
                        df_podcast_dive['consumed_at'] = pd.to_datetime(df_podcast_dive['consumed_at'], errors='coerce')
                        df_podcast_dive.dropna(subset=['consumed_at'], inplace=True)

                        if not df_podcast_dive.empty:
                            df_podcast_dive['year_month'] = df_podcast_dive['consumed_at'].dt.to_period('M').astype(str)
                            df_podcast_dive.loc[:, 'eq_full'] = pd.to_numeric(df_podcast_dive['eq_full'], errors='coerce').fillna(0)
                            podcast_monthly_agg = df_podcast_dive.groupby(['year_month', 'title'])['eq_full'].sum().reset_index()
                            podcast_monthly_agg = podcast_monthly_agg.sort_values('year_month')

                            if not podcast_monthly_agg.empty and podcast_monthly_agg['eq_full'].sum() > 0:
                                fig_podcast_trend = px.line(
                                    podcast_monthly_agg,
                                    x='year_month',
                                    y='eq_full',
                                    color='title',
                                    title="Monthly Downloads for Selected Podcast(s)",
                                    labels={'year_month': 'Month', 'eq_full': 'Equivalent Full Downloads', 'title': 'Podcast'},
                                    markers=True
                                )
                                fig_podcast_trend.update_xaxes(type='category')
                                st.plotly_chart(fig_podcast_trend, use_container_width=True)
                            else:
                                st.info("No monthly download data for the selected podcast(s) with current filters (or all values are zero).")
                        else:
                            st.info("No valid 'consumed_at' dates available for selected podcast(s) after filtering.")
                    else:
                        st.info("Not enough data or required columns missing for selected podcast(s) trend chart.")
                else:
                    st.info("Select one or more podcasts to see their download trends.")
            else:
                st.info("No podcast titles available with current filters to select for a deep dive.")
        else:
            st.info("No 'title' column available or data empty for podcast deep dive.")

    with tab3:
        st.header("Feature & Bandwidth Insights")

        # Chart 3.1: Downloads by Feature
        if not df_filtered.empty and 'feature' in df_filtered.columns and 'eq_full' in df_filtered.columns:
            st.subheader("Downloads by Feature")
            df_filtered.loc[:, 'eq_full'] = pd.to_numeric(df_filtered['eq_full'], errors='coerce').fillna(0)
            feature_downloads = df_filtered.groupby('feature')['eq_full'].sum().reset_index()
            feature_downloads = feature_downloads[feature_downloads['eq_full'] > 0] # Only show features with downloads
            
            if not feature_downloads.empty:
                fig_feature_downloads = px.bar(
                    feature_downloads, 
                    x='feature', 
                    y='eq_full',
                    title="Total Equivalent Full Downloads by Feature",
                    labels={'feature': 'Feature', 'eq_full': 'Total Eq. Full Downloads'}
                )
                st.plotly_chart(fig_feature_downloads, use_container_width=True)
            else:
                st.info("No download data available by feature with current filters (or all values are zero).")
        else:
            st.info("Required columns ('feature', 'eq_full') not available or data is empty for 'Downloads by Feature' chart.")

        # Chart 3.2: Total Bandwidth Over Time (Monthly)
        if not df_filtered.empty and 'consumed_at' in df_filtered.columns and 'total_bw' in df_filtered.columns:
            st.subheader("Total Bandwidth Over Time (Monthly)")
            monthly_bw = df_filtered.copy()
            monthly_bw['consumed_at'] = pd.to_datetime(monthly_bw['consumed_at'], errors='coerce')
            monthly_bw.dropna(subset=['consumed_at'], inplace=True)
            
            if not monthly_bw.empty:
                monthly_bw['year_month'] = monthly_bw['consumed_at'].dt.to_period('M').astype(str)
                monthly_bw.loc[:, 'total_bw'] = pd.to_numeric(monthly_bw['total_bw'], errors='coerce').fillna(0)
                monthly_bw_agg = monthly_bw.groupby('year_month')['total_bw'].sum().reset_index()
                monthly_bw_agg = monthly_bw_agg.sort_values('year_month')
                monthly_bw_agg['total_bw_gb'] = monthly_bw_agg['total_bw'] / (1024**3) # Convert bytes to GB

                if not monthly_bw_agg.empty and monthly_bw_agg['total_bw_gb'].sum() > 0:
                    fig_monthly_bw_trend = px.line(
                        monthly_bw_agg,
                        x='year_month',
                        y='total_bw_gb',
                        title="Total Bandwidth (GB) per Month",
                        labels={'year_month': 'Month', 'total_bw_gb': 'Total Bandwidth (GB)'},
                        markers=True
                    )
                    fig_monthly_bw_trend.update_xaxes(type='category')
                    st.plotly_chart(fig_monthly_bw_trend, use_container_width=True)
                else:
                    st.info("No data available for 'Total Bandwidth Over Time' chart with current filters (or all values are zero).")
            else:
                st.info("No valid 'consumed_at' dates available after filtering for 'Total Bandwidth Over Time' chart.")
        else:
            st.info("Required columns ('consumed_at', 'total_bw') not available or data is empty for 'Total Bandwidth Over Time' chart.")

# This allows the script to be run directly for testing (optional)
# For a multipage app, Home.py is the entry point, and this page will be discovered.
# if __name__ == "__main__":
# render() # Changed from run_analytics to render 

render() # Call the render function to display the page content 