import sqlite3
import pandas as pd
import numpy as np

DB_PATH = r"C:\Users\kanik\Documents\Codex\2026-07-03\files-mentioned-by-the-user-build\data\full_4y.db"

def main():
    print("Connecting to database...")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    
    report_lines = []
    report_lines.append("# Data Quality Report")
    report_lines.append("\n## Database Overview")
    
    # Row Counts
    events_count = pd.read_sql("SELECT COUNT(*) as c FROM events", conn)['c'].iloc[0]
    market_data_count = pd.read_sql("SELECT COUNT(*) as c FROM market_data", conn)['c'].iloc[0]
    event_returns_count = pd.read_sql("SELECT COUNT(*) as c FROM event_returns", conn)['c'].iloc[0]
    
    report_lines.append(f"- **events**: {events_count:,} rows")
    report_lines.append(f"- **market_data**: {market_data_count:,} rows")
    report_lines.append(f"- **event_returns**: {event_returns_count:,} rows")
    
    # Events Analysis
    report_lines.append("\n## Events Table Analysis")
    events_df = pd.read_sql("SELECT id, timestamp_utc, raw_text FROM events", conn)
    
    # Date coverage
    events_df['datetime'] = pd.to_datetime(events_df['timestamp_utc'], errors='coerce')
    min_date = events_df['datetime'].min()
    max_date = events_df['datetime'].max()
    report_lines.append(f"- **Date Coverage**: {min_date} to {max_date}")
    
    # Empty texts
    empty_texts = events_df['raw_text'].isna() | (events_df['raw_text'].str.strip() == '')
    report_lines.append(f"- **Empty or Media-only Posts (no text)**: {empty_texts.sum():,} posts")
    
    # Missing / Malformed
    missing_timestamps = events_df['timestamp_utc'].isna().sum()
    report_lines.append(f"- **Missing Timestamps**: {missing_timestamps}")
    
    # Timezone check
    tz_aware = events_df['timestamp_utc'].str.contains(r'(\+|-)\d{2}:\d{2}$|Z$', regex=True).fillna(False)
    report_lines.append(f"- **Timezone Inconsistent (missing UTC offset)**: {(~tz_aware).sum():,} posts")
    
    # Event Returns Analysis
    report_lines.append("\n## Event Returns Analysis")
    
    # Invalid VIX
    vix_count = pd.read_sql("SELECT COUNT(*) as c FROM event_returns WHERE asset = 'VIX'", conn)['c'].iloc[0]
    vix_valid_count = pd.read_sql("SELECT COUNT(*) as c FROM event_returns WHERE asset = '^VIX'", conn)['c'].iloc[0]
    report_lines.append(f"- **Invalid VIX rows (asset='VIX')**: {vix_count:,}")
    report_lines.append(f"- **Valid VIX rows (asset='^VIX')**: {vix_valid_count:,}")
    
    # Partial History & No Data
    partial_history = pd.read_sql("SELECT COUNT(*) as c FROM event_returns WHERE status = 'partial_history'", conn)['c'].iloc[0]
    no_data = pd.read_sql("SELECT COUNT(*) as c FROM event_returns WHERE status = 'no_data'", conn)['c'].iloc[0]
    report_lines.append(f"- **Partial History (recent events)**: {partial_history:,} rows")
    report_lines.append(f"- **No Data Status**: {no_data:,} rows")
    
    # Outliers
    outliers_df = pd.read_sql("""
        SELECT COUNT(*) as c 
        FROM event_returns 
        WHERE status = 'success' AND (return_1d > 0.5 OR return_1d < -0.5 OR return_1w > 1.0 OR return_1w < -1.0)
    """, conn)
    report_lines.append(f"- **Return Outliers (e.g. >50% daily or >100% weekly)**: {outliers_df['c'].iloc[0]:,} rows")
    
    # Asset Summary
    print("Generating asset summary...")
    asset_summary = pd.read_sql("""
        SELECT asset, status, COUNT(*) as count
        FROM event_returns
        GROUP BY asset, status
    """, conn)
    
    # Pivot to get nice table
    asset_pivot = asset_summary.pivot(index='asset', columns='status', values='count').fillna(0).astype(int)
    asset_pivot['Total'] = asset_pivot.sum(axis=1)
    
    asset_pivot.to_csv('analysis_output/asset_summary.csv')
    
    report_lines.append("\n## Asset Status Summary")
    report_lines.append("Detailed counts exported to `analysis_output/asset_summary.csv`.")
    
    with open("analysis_output/data_quality_report.md", "w", encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print("Done. Reports generated.")
    conn.close()

if __name__ == "__main__":
    main()
