import streamlit as st
import pandas as pd
import sqlite3

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
    st.subheader("Explore Downloads")

    with st.sidebar:
        if "feature" in df.columns:
            all_features = sorted(df["feature"].dropna().unique(), key=str)
            selected_features = st.multiselect("Filter by Feature:", all_features, default=all_features)
            df = df[df["feature"].isin(selected_features)]

        if "consumed_at" in df.columns:
            df["consumed_at"] = pd.to_datetime(df["consumed_at"])
            date_min = df["consumed_at"].min()
            date_max = df["consumed_at"].max()
            start_date, end_date = st.date_input("Filter by Consumption Date:", [date_min, date_max])
            df = df[(df["consumed_at"] >= start_date) & (df["consumed_at"] <= end_date)]

        if "title" in df.columns:
            title_search = st.text_input("Search Title:", "")
            if title_search:
                df = df[df["title"].str.contains(title_search, case=False, na=False)]

    expected_cols = ["feature", "title", "code", "consumed_at", "created_at", "eq_full", "full", "partial"]
    df = df.sort_values("eq_full", ascending=False)

    missing = [col for col in expected_cols if col not in df.columns]
    if missing:
        st.warning(f"⚠️ Missing columns in database: {missing}")
        st.write("📌 Available columns:", list(df.columns))
        st.dataframe(df, use_container_width=True)
    else:
        st.dataframe(df[expected_cols], use_container_width=True)

with raw_tab:
    st.subheader("Raw Table View")
    st.dataframe(df, use_container_width=True)

with upload_tab:
    st.subheader("Upload Spreadsheet")
    uploaded_file = st.file_uploader("Choose a .xlsx file", type="xlsx")
    if uploaded_file:
        st.warning("Upload functionality not implemented yet in this UI.")

st.caption("Data source: podcasts.db — showing {} rows".format(len(df)))
