import streamlit as st
import pandas as pd

def render(df):
    st.subheader("Explore Downloads")

    with st.sidebar:
        st.markdown("### Filters")

        # Feature filter
        features = sorted(df["feature"].dropna().unique().tolist())
        selected_features = st.multiselect("Feature", features, default=features)
        df = df[df["feature"].isin(selected_features)] if selected_features else df

        # Sheet/year dropdown filter
        if "sheet_name" in df.columns:
            years = sorted(df["sheet_name"].dropna().unique())
            selected_years = st.multiselect("Sheet Year", years, default=years)
            df = df[df["sheet_name"].isin(selected_years)] if selected_years else df

    df_clean = df.reset_index(drop=True)
    st.dataframe(df_clean)