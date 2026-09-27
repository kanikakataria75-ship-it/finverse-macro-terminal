import sqlite3
import pandas as pd

DB_PATH = r"C:\Users\kanik\Documents\Codex\2026-07-03\files-mentioned-by-the-user-build\data\full_4y.db"

try:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    
    print("--- TABLES ---")
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
    print(tables)
    
    for table in tables['name']:
        print(f"\n--- SCHEMA FOR {table} ---")
        schema = pd.read_sql(f"PRAGMA table_info({table});", conn)
        print(schema[['name', 'type', 'notnull', 'pk']])
        
        count = pd.read_sql(f"SELECT COUNT(*) as count FROM {table};", conn)
        print(f"Row count: {count['count'].iloc[0]}")
        
        print(f"\nSample data from {table}:")
        sample = pd.read_sql(f"SELECT * FROM {table} LIMIT 3;", conn)
        print(sample)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
