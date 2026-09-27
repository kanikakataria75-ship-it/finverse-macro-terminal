# Executive Summary

## A. Verified Findings
- **Data Integrity:** The initial database contained 33,498 events and 937,944 event/asset calculations. A significant portion of events either lacked text (media-only) or were highly clustered temporally. 
- **Clustering Impact:** After collapsing events occurring within a 60-minute window, we identified that post-weighted metrics drastically overrepresented days with high posting volumes. Session-weighting (using clusters) provides a statistically sound foundation for analysis by isolating unique independent observations.
- **VIX Correction:** We identified and isolated invalid data mapped to the plain `VIX` ticker, relying strictly on `^VIX` for volatility analysis.
- **Return Distributions:** Broadly, post-event 1-day returns for the S&P 500 do not exhibit massive divergence from unconditional market drift. Most action falls within a typical daily standard deviation. 

## B. Market-Regime Effects
- Baseline (unconditional) returns across the four-year dataset heavily dictate forward expectations. For instance, the general upward drift of the S&P 500 (`^GSPC`) introduces a positive bias to 1-week and 1-month returns following *any* post.
- Abnormal return calculations—which subtract this baseline regime—demonstrate that simply holding the asset yields similar performance to trading on the event signals generically.

## C. Possible but Unproven Post-Related Patterns
- Topics mapped to specific macroeconomic themes (e.g., China, Tariffs, Fed) show varied mean returns, but applying rigorous bootstrapped confidence intervals reveals that most 1-week abnormal returns cross zero. 
- Some micro-effects may exist on very short intraday horizons, but at the session (1-day, 1-week) level, strong directional predictability is unproven and easily lost to market noise.

## D. Data Limitations
- **Partial History:** Recent events lack full forward lookahead (e.g., missing 1-month returns). These were successfully flagged and excluded from the outcome analysis.
- **Oversimplified Topic Matching:** The regex-based topic extraction provides a transparent and auditable method but likely misses nuanced contexts, sarcasm, or complex multi-topic implications that an advanced LLM might catch.
- **Endogeneity:** Posts often *react* to market moves rather than *cause* them. Parsing the direction of causality remains a structural limitation of this dataset.

## E. Recommended Next Actions
1. **Refine Signal Granularity:** Move beyond end-of-day or session returns to evaluate high-frequency, minute-by-minute order book reactions following high-impact clusters.
2. **Advanced NLP:** Upgrade the regex-based topic modeling to a lightweight, locally hosted LLM classifier (e.g., Llama 3 or FinBERT) for more robust semantic understanding.
3. **Model Development with Caution:** As per the `modeling_plan.md`, develop a strictly regularized linear baseline with chronological holdout sets before committing to complex predictive models. Focus on probability calibration to manage risk appropriately.
