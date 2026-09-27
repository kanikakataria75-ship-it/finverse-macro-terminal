# Modeling Plan

## Overview
This document proposes a predictive modeling framework that leverages the cleaned event-study data to forecast abnormal market returns based on Truth Social activity. **Training is explicitly deferred; this plan outlines the necessary guardrails to ensure valid causal and predictive inference.**

## Input Features and Prediction Targets
- **Inputs:**
  - `topic_string` and boolean topic flags.
  - NLP embeddings (e.g., FinBERT) of the `raw_text` from the clustered events.
  - Market regime indicators (e.g., prior 1-week S&P 500 return, prior VIX level).
  - Time-of-day or session context.
- **Targets:**
  - Binary classification: Outperforming the unconditional market drift over a 1-day or 3-day horizon (e.g., `abnormal_return > 0`).
  - Regression: The continuous `abnormal_return` metric.

## Splitting Strategy
- **Chronological Splits:** Standard random k-fold cross-validation will cause severe data leakage due to overlapping market regimes and temporal autocorrelation.
- **Train/Validation/Test:** Use strict time-based splitting (e.g., Train: 2021-2023, Val: early 2024, Test: late 2024/recent).
- **Cluster Isolation:** Ensure no cluster is split across boundaries, and allow a temporal gap (e.g., 2 weeks) between sets to prevent overlapping forward returns from bleeding across splits.

## Baselines
- **Always-Long:** Simply predicting positive drift for equities (as the S&P 500 trends upward historically).
- **Random Walk / Naive Model:** Predicting zero abnormal return.
- **Momentum:** Predicting that the return will match the previous day's return direction.

## Probability Calibration
Raw accuracy is an insufficient metric because it does not account for the confidence of predictions, class imbalances, or asymmetric financial payoff structures.
- Models should output calibrated probabilities (e.g., via Platt scaling or Isotonic Regression).
- Precision and Recall on the top decile of predicted probabilities are far more relevant than global accuracy.

## Recommendation on Proceeding
**Conclusion:** Before executing a full training loop, exploratory data analysis indicates high variance and wide confidence intervals for many topics. The evidence suggests that while there may be micro-effects, generating a high-Sharpe trading model purely on this data will be extremely challenging. We recommend proceeding with simple linear baselines (Logistic Regression with L1 regularization) before attempting complex deep learning architectures.
