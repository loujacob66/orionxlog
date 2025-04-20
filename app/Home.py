import streamlit as st
from Explore import render as render_explore
from Upload import render as render_upload
import pandas as pd
import sqlite3

st.set_page_config(layout="wide")

def load_db():
    db_path = "data/podcasts.db"
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM podcasts", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Failed to load database: {e}")
        return pd.DataFrame()

st.title("📊 OrionX Podcast Trends")

df = load_db()
tab1, tab2, tab3 = st.tabs(["Explore Data", "Raw Table View", "Upload Data"])

with tab1:
    if not df.empty:
        render_explore(df)
    else:
        st.warning("No data found. Try uploading an Excel file in the Upload tab.")

with tab2:
    if not df.empty:
        st.dataframe(df)
    else:
        st.info("No data to display.")

with tab3:
    render_upload()