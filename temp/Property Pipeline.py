import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from utils.database import get_db_connection, get_all_listings, get_summary_stats

# Configuration
st.set_page_config(
    page_title="Property Pipeline Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Define paths
if 'base_path' not in st.session_state:
    st.session_state['base_path'] = Path(__file__).parent.parent
    # Default paths
    st.session_state['default_db_path'] = "../property-pipeline/data/listings.db"
    st.session_state['default_scripts_path'] = "../property-pipeline/scripts"
    st.session_state['default_config_path'] = "../property-pipeline/config"

# Sidebar for configuration
with st.sidebar:
    st.title("Configuration")
    # Database path
    db_path = st.text_input(
        "Database Path", 
        value=str(st.session_state['default_db_path']),
        help="Path to your listings.db SQLite database"
    )
    st.session_state['db_path'] = db_path
    # Quick links
    st.subheader("Quick Links")
    st.write("Navigate to:")
    st.page_link("pages/01_Dashboard.py", label="📊 Dashboard", icon="📊")
    st.page_link("pages/02_Property_Explorer.py", label="🔍 Property Explorer", icon="🔍")
    st.page_link("pages/03_Data_Enrichment.py", label="🔄 Data Enrichment", icon="🔄")
    st.page_link("pages/04_Analytics.py", label="📈 Analytics", icon="📈")

# Main content
st.title("Property Pipeline Dashboard")
st.write("""
Welcome to the Property Pipeline Dashboard. This application helps you visualize and manage your real estate property data.
Use the sidebar to navigate between different views.
""")

# Check database connection
try:
    # Try to connect to the database
    conn = get_db_connection(db_path)
    df = get_all_listings(db_path, limit=5)
    conn.close()
    
    if df.empty:
        st.warning("Database connected, but no data found. Use the Data Enrichment page to populate your database.")
    else:
        pass
        
        # Display some key metrics
        st.header("Quick Stats")
        
        try:
            stats = get_summary_stats(db_path)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Properties", f"{stats['total_count']:,}")
            
            with col2:
                avg_price = stats['avg_price']
                if avg_price:
                    st.metric("Average Price", f"${avg_price:,.0f}")
                else:
                    st.metric("Average Price", "N/A")
            
            with col3:
                avg_sqft = stats['avg_sqft']
                if avg_sqft:
                    st.metric("Average Sqft", f"{avg_sqft:,.0f}")
                else:
                    st.metric("Average Sqft", "N/A")
            
            with col4:
                avg_price_per_sqft = stats['avg_price_per_sqft']
                if avg_price_per_sqft:
                    st.metric("Avg Price/Sqft", f"${avg_price_per_sqft:,.0f}")
                else:
                    st.metric("Avg Price/Sqft", "N/A")
            
            # Sample of recent listings
            st.header("Recent Listings")
            # Select all rows and columns starting from the third column (index 2)
            df_display = df.iloc[:, 1:]
            st.dataframe(df_display, use_container_width=True)
            
            # Link to explore more
            st.write("Use the Property Explorer page to see more listings and apply filters.")
            st.page_link("pages/02_Property_Explorer.py", label="Go to Property Explorer", icon="🔍")
            
        except Exception as e:
            st.error(f"Error getting statistics: {e}")
            
except Exception as e:
    st.error(f"Error connecting to database: {e}")
    st.info(f"Make sure the database exists at: {db_path}")
    
    # Show init button
    if st.button("Initialize Database"):
        from utils.script_runner import run_init_db
        
        init_script_path = Path(st.session_state['default_scripts_path']) / "init_db.py"
        if init_script_path.exists():
            with st.spinner("Initializing database..."):
                result = run_init_db(init_script_path)
                
                if result['returncode'] == 0:
                    st.success("Database initialized successfully!")
                    st.experimental_rerun()
                else:
                    st.error("Failed to initialize database")
                    st.text_area("Error", result['stderr'], height=200)
        else:
            st.error(f"Init script not found at: {init_script_path}")
