# Methodology

## Overview
This document outlines the methodological framework used to process, clean, and analyze the Truth Social event-study database (`full_4y.db`).

## Data Ingestion and Validation
1. **Source Integrity:** The database was accessed in read-only mode to prevent any modification to the raw dataset.
2. **Exclusion Criteria:**
   - Rows matching `asset = 'VIX'` were excluded, as plain VIX has no valid market data; `^VIX` is retained.
   - Rows marked as `status = 'no_data'` were discarded.
   - `status = 'partial_history'` was preserved for the dataset but excluded from the outcome statistical analysis to avoid truncation bias.
   - Posts with empty texts or containing only media URLs were excluded from semantic topic assignment.

## Session Clustering
Given the high frequency of posts occurring during single market sessions, treating every post as an independent observation artificially inflates sample sizes and biases standard errors.
- **Approach:** We ordered all events chronologically and clustered any posts that occurred within 60 minutes of the previous post.
- **Session-Weighting vs Post-Weighting:** 
  - *Session-weighted* data groups all posts in a cluster into a single independent observation. Topics from multiple posts in the same cluster are merged.
  - *Post-weighted* metrics measure returns unconditionally against each post. We explicitly contrasted both approaches in our findings.

## Topic Extraction
Topics were extracted using a transparent, regex-based keyword matching algorithm rather than an opaque LLM-based classifier.
- A single cluster can be assigned multiple topics if the combined posts trigger different regex rules.
- See `topic_summary.csv` for keyword distributions.
- **Categories include:** Tariffs, China, Federal Reserve, Inflation, Oil/Energy, Geopolitics, Stocks, Crypto, Fiscal Policy, and Elections.

## Statistical Evaluation
1. **Baselines:** We calculated the unconditional average return for each asset across all days in the dataset to act as the expected market drift.
2. **Abnormal Returns:** Calculated by subtracting the baseline from the post-conditioned return.
3. **Bootstrapping:** We utilized non-parametric bootstrapping with 1,000 resamples on the *cluster level* to construct 95% confidence intervals, mitigating issues related to non-normal return distributions.
