import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import streamlit as st
import pandas as pd
import sqlite3
from app.Explore import render as render_explore

st.set_page_config(page_title="OrionX Podcast Trends", layout="wide")
st.write("✅ Home.py is executing — version updated!")

DB_PATH = "data/podcasts.db"

@st.cache_data(ttl=60)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM podcasts", conn)
    conn.close()
    return df

# Load data
st.title("📊 OrionX Podcast Trends")
df = load_data()

# Tabs
explore_tab, raw_tab, upload_tab = st.tabs(["Explore Data", "Raw Table View", "Upload Data"])

with explore_tab:
    render_explore(df)

with raw_tab:
    st.dataframe(df)

with upload_tab:
    st.write("📤 Upload tab placeholder (future functionality)")