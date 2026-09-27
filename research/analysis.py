import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

DB_PATH = r"C:\Users\kanik\Documents\Codex\2026-07-03\files-mentioned-by-the-user-build\data\full_4y.db"

def bootstrap_ci(data, num_samples=1000, ci=95):
    if len(data) == 0:
        return np.nan, np.nan
    boot_means = []
    for _ in range(num_samples):
        sample = np.random.choice(data, size=len(data), replace=True)
        boot_means.append(np.mean(sample))
    lower = np.percentile(boot_means, (100 - ci) / 2)
    upper = np.percentile(boot_means, 100 - (100 - ci) / 2)
    return lower, upper

def main():
    print("Loading datasets...")
    clusters = pd.read_csv('analysis_output/clean_event_clusters.csv')
    session_returns = pd.read_csv('analysis_output/clean_event_returns.csv')
    
    # Load raw returns for post-weighted stats
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    raw_returns = pd.read_sql("SELECT event_id, asset, return_1d, return_3d, return_1w, return_2w, return_1m, status FROM event_returns WHERE asset != 'VIX' AND status != 'no_data'", conn)
    market_data = pd.read_sql("SELECT asset, datetime_utc, close FROM market_data", conn)
    events_raw = pd.read_sql("SELECT id, timestamp_utc FROM events", conn)
    conn.close()
    
    # Exclude partial history for outcome analysis
    session_returns = session_returns[session_returns['is_partial_history'] == False]
    raw_returns = raw_returns[raw_returns['status'] == 'success']
    
    # Join raw returns with cluster ID to get post-weighted with topics
    post_returns = pd.merge(raw_returns, clusters[['id', 'cluster_id', 'topic_string']], left_on='event_id', right_on='id', how='inner')
    
    report_lines = []
    report_lines.append("# Key Findings")
    report_lines.append("\n## Overall Market Patterns (Session-Weighted vs Post-Weighted)")
    
    # Calculate overall stats for S&P 500 (^GSPC) as a proxy for the market
    sp500_session = session_returns[session_returns['asset'] == '^GSPC']
    sp500_post = post_returns[post_returns['asset'] == '^GSPC']
    
    def get_stats(df, prefix=""):
        return {
            f'{prefix}N': len(df),
            f'{prefix}Mean_1d': df['return_1d'].mean(),
            f'{prefix}Median_1d': df['return_1d'].median(),
            f'{prefix}Std_1d': df['return_1d'].std(),
            f'{prefix}PosRate_1d': (df['return_1d'] > 0).mean(),
        }
    
    sess_stats = get_stats(sp500_session, "Session_")
    post_stats = get_stats(sp500_post, "Post_")
    
    report_lines.append(f"- **Unique Independent Session-Level Observations (SPY/GSPC)**: {sess_stats['Session_N']}")
    report_lines.append(f"- **Total Post-Level Observations (SPY/GSPC)**: {post_stats['Post_N']}")
    report_lines.append(f"- **Session-Weighted Mean 1d Return**: {sess_stats['Session_Mean_1d']:.4f} (Pos Rate: {sess_stats['Session_PosRate_1d']:.1%})")
    report_lines.append(f"- **Post-Weighted Mean 1d Return**: {post_stats['Post_Mean_1d']:.4f} (Pos Rate: {post_stats['Post_PosRate_1d']:.1%})")
    
    report_lines.append("\n*Note: Post-weighted statistics often over-represent market outcomes that occur on days with high posting volume, artificially inflating N and biasing the mean. Session-weighting (clustering posts within 60 minutes) corrects this dependency.*")
    
    # Baselines
    report_lines.append("\n## Baselines (Unconditional Returns)")
    market_data['datetime'] = pd.to_datetime(market_data['datetime_utc']).dt.tz_localize(None)
    market_data = market_data.sort_values(['asset', 'datetime'])
    market_data['ret_1d'] = market_data.groupby('asset')['close'].pct_change()
    unconditional_means = market_data.groupby('asset')['ret_1d'].mean()
    
    gspc_baseline = unconditional_means.get('^GSPC', 0)
    report_lines.append(f"- **^GSPC Unconditional Mean 1d Return**: {gspc_baseline:.4f}")
    
    # Topic Analysis
    report_lines.append("\n## Topic-Specific Outcomes (^GSPC 1w Returns)")
    report_lines.append("Topic | N (Clusters) | Mean 1w | 95% CI Lower | 95% CI Upper | Abnormal 1w")
    report_lines.append("---|---|---|---|---|---")
    
    # Calculate 1w baseline
    gspc_1w_baseline = gspc_baseline * 5 # Approx
    
    # Flatten topics for session returns
    # session_returns has cluster_id, we need topics
    session_with_topics = pd.merge(session_returns, clusters[['cluster_id', 'topic_string']], on='cluster_id')
    
    # explode topics
    session_with_topics['topic_list'] = session_with_topics['topic_string'].str.split('|')
    exploded = session_with_topics.explode('topic_list')
    exploded = exploded[exploded['asset'] == '^GSPC']
    
    topic_results = []
    
    plt.figure(figsize=(12, 8))
    
    for topic, group in exploded.groupby('topic_list'):
        returns_1w = group['return_1w'].dropna().values
        n = len(returns_1w)
        if n < 5:
            continue
        mean_ret = np.mean(returns_1w)
        ci_lower, ci_upper = bootstrap_ci(returns_1w, ci=95)
        abnormal = mean_ret - gspc_1w_baseline
        topic_results.append({
            'Topic': topic,
            'N': n,
            'Mean_1w': mean_ret,
            'CI_Lower': ci_lower,
            'CI_Upper': ci_upper,
            'Abnormal_1w': abnormal
        })
        report_lines.append(f"{topic} | {n} | {mean_ret:.4f} | {ci_lower:.4f} | {ci_upper:.4f} | {abnormal:.4f}")
        
    # Plotting
    res_df = pd.DataFrame(topic_results)
    if not res_df.empty:
        res_df = res_df.sort_values('Mean_1w')
        plt.barh(res_df['Topic'], res_df['Mean_1w'], xerr=[res_df['Mean_1w'] - res_df['CI_Lower'], res_df['CI_Upper'] - res_df['Mean_1w']], capsize=5)
        plt.axvline(gspc_1w_baseline, color='red', linestyle='--', label='Baseline')
        plt.title('Mean 1-Week Return by Topic (^GSPC)')
        plt.xlabel('Return')
        plt.legend()
        plt.tight_layout()
        plt.savefig('analysis_output/charts/topic_1w_returns.png')
        
    plt.close()
    
    # Asset distributions
    plt.figure(figsize=(10, 6))
    assets_to_plot = ['^GSPC', '^IXIC', 'GC=F', 'CL=F']
    for asset in assets_to_plot:
        data = session_returns[(session_returns['asset'] == asset) & (session_returns['return_1d'].notna())]['return_1d']
        sns.kdeplot(data, label=asset)
    plt.axvline(0, color='black', linestyle='--')
    plt.title('1-Day Return Distributions Following Events')
    plt.legend()
    plt.tight_layout()
    plt.savefig('analysis_output/charts/asset_distributions.png')
    plt.close()
    
    report_lines.append("\n## Stability & Multiple Testing")
    report_lines.append("Given the overlap of multiple topics and multiple horizons (1d, 3d, 1w, 2w, 1m), we caution against p-hacking. The confidence intervals are provided for exploratory purposes. Topics showing intervals crossing the baseline (or zero) should be treated as non-significant.")
    
    with open('analysis_output/key_findings.md', 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print("Done statistical analysis.")

if __name__ == "__main__":
    main()
