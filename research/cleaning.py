import sqlite3
import pandas as pd
import numpy as np
import re
from datetime import timedelta

DB_PATH = r"C:\Users\kanik\Documents\Codex\2026-07-03\files-mentioned-by-the-user-build\data\full_4y.db"

# Define topics and keywords
TOPICS = {
    'Tariffs and trade': r'\b(tariff|trade war|wto|nafta|usmca|import tax|duties|duty)\b',
    'China': r'\b(china|chinese|beijing|ccp|xi jinping)\b',
    'Federal Reserve and interest rates': r'\b(fed|federal reserve|powell|interest rate|yellen|fomc|basis point|rates?)\b',
    'Inflation': r'\b(inflation|cpi|ppi|prices|cost of living)\b',
    'Oil and energy': r'\b(oil|energy|gas|opec|barrel|crude|gasoline)\b',
    'War, sanctions and geopolitics': r'\b(war|sanction|military|ukraine|russia|israel|middle east|nato|putin|zelensky|gaza)\b',
    'Companies and individual stocks': r'\b(stock|nasdaq|s&p|apple|tesla|amazon|google|meta|company|corporate|earnings|wall street)\b',
    'Cryptocurrency': r'\b(crypto|bitcoin|btc|ethereum|eth|digital currency|blockchain)\b',
    'Fiscal policy and government spending': r'\b(debt|deficit|spending|stimulus|tax cut|taxes|budget)\b',
    'Elections and domestic politics': r'\b(election|vote|democrat|republican|biden|trump|congress|senate|kamala|harris)\b',
}

def extract_topics(text):
    if not isinstance(text, str) or not text.strip():
        return ['Other/non-macro posts']
    
    text = text.lower()
    matched_topics = []
    for topic, pattern in TOPICS.items():
        if re.search(pattern, text):
            matched_topics.append(topic)
            
    if not matched_topics:
        matched_topics.append('Other/non-macro posts')
    
    return matched_topics

def main():
    print("Loading data...")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    events = pd.read_sql("SELECT * FROM events", conn)
    returns = pd.read_sql("SELECT * FROM event_returns WHERE asset != 'VIX' AND status != 'no_data'", conn)
    conn.close()
    
    # Process events
    events['datetime'] = pd.to_datetime(events['timestamp_utc'], errors='coerce')
    events = events.dropna(subset=['datetime']).sort_values('datetime')
    
    print("Clustering events within 60 minutes...")
    cluster_ids = []
    current_cluster_id = 0
    last_time = None
    
    for dt in events['datetime']:
        if last_time is None:
            current_cluster_id += 1
            last_time = dt
        else:
            diff = (dt - last_time).total_seconds()
            if diff > 3600:
                current_cluster_id += 1
            last_time = dt
        cluster_ids.append(current_cluster_id)
        
    events['cluster_id'] = cluster_ids
    
    print("Extracting topics...")
    events['topics'] = events['raw_text'].apply(extract_topics)
    
    # Aggregate topics per cluster (union of topics)
    cluster_topics = events.groupby('cluster_id')['topics'].agg(lambda x: list(set([item for sublist in x for item in sublist]))).reset_index()
    
    # Keep the earliest event per cluster as the representative one for basic info
    clusters = events.groupby('cluster_id').first().reset_index()
    clusters = clusters.drop(columns=['topics'])
    clusters = pd.merge(clusters, cluster_topics, on='cluster_id')
    
    clusters['topic_string'] = clusters['topics'].apply(lambda x: '|'.join(x))
    
    # Save clean event clusters
    clean_clusters = clusters[['cluster_id', 'id', 'post_id', 'datetime', 'author', 'raw_text', 'url', 'topic_string']]
    clean_clusters.to_csv('analysis_output/clean_event_clusters.csv', index=False)
    
    # Process event returns
    print("Processing event returns...")
    
    # Join returns with events to get cluster_id
    returns = pd.merge(returns, events[['id', 'cluster_id']], left_on='event_id', right_on='id', how='inner')
    
    # Drop duplicates for the same asset within the same cluster, taking the mean of returns
    # But wait, returns are measured based on market session.
    # If two posts are in the same cluster, they likely align to the same session.
    # We will average the returns for the same asset in the same cluster to eliminate duplication.
    # But before averaging, let's make sure we keep flags.
    
    # Flag partial history
    returns['is_partial_history'] = returns['status'] == 'partial_history'
    
    agg_funcs = {
        'return_1d': 'mean',
        'return_3d': 'mean',
        'return_1w': 'mean',
        'return_2w': 'mean',
        'return_1m': 'mean',
        'max_drawdown': 'mean',
        'max_gain': 'mean',
        'volatility': 'mean',
        'largest_positive_move': 'mean',
        'largest_negative_move': 'mean',
        'is_partial_history': 'max', # True if any is true
        'status': 'first'
    }
    
    clean_returns = returns.groupby(['cluster_id', 'asset']).agg(agg_funcs).reset_index()
    clean_returns.to_csv('analysis_output/clean_event_returns.csv', index=False)
    
    # Topic Summary
    print("Generating topic summary...")
    topic_counts = {}
    for topics in clusters['topics']:
        for t in topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
            
    topic_summary = pd.DataFrame(list(topic_counts.items()), columns=['Topic', 'Cluster_Count'])
    topic_summary = topic_summary.sort_values('Cluster_Count', ascending=False)
    topic_summary.to_csv('analysis_output/topic_summary.csv', index=False)
    
    print("Done clustering and cleaning.")

if __name__ == "__main__":
    main()
