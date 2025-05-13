import pandas as pd
import sqlite3
import os
import sys

# It's good practice to ensure the project root is handled consistently
# if this utils file might be imported from different depths.
# However, if Home.py and pages/* are the only importers, 
# their own path setup might be sufficient.
# For simplicity, let's assume the caller (Home.py, Explore.py) handles sys.path.
# _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) # if utils is in app/
# if _project_root not in sys.path:
#     sys.path.insert(0, _project_root)

def load_db():
    # We need to define where Home.py's _project_root equivalent would be from utils.py perspective
    # Assuming utils.py is in app/, then '..' goes to project root.
    utils_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    db_path = os.path.join(utils_project_root, "data", "podcasts.db")
    try:
        if not os.path.exists(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            return pd.DataFrame() 
            
        conn = sqlite3.connect(db_path)
        table_check_query = "SELECT name FROM sqlite_master WHERE type='table' AND name='podcasts';"
        cursor = conn.cursor()
        cursor.execute(table_check_query)
        if cursor.fetchone() is None:
            conn.close()
            return pd.DataFrame()

        # Debug: Print the SQL query result
        print("Loading data from database...")
        df = pd.read_sql_query("SELECT * FROM podcasts", conn)
        print(f"Loaded {len(df)} rows from database")
        print("Years in data:", sorted(df["consumed_year"].unique().tolist()))
        
        # Ensure consumed_year is numeric
        df["consumed_year"] = pd.to_numeric(df["consumed_year"], errors='coerce')
        df = df.dropna(subset=["consumed_year"])
        df["consumed_year"] = df["consumed_year"].astype(int)
        
        conn.close()
        return df
    except sqlite3.Error as e:
        print(f"SQLite error in utils.load_db: {e}") # Log to console for debugging
        return pd.DataFrame()
    except Exception as e:
        print(f"General error in utils.load_db: {e}") # Log to console
        return pd.DataFrame() 