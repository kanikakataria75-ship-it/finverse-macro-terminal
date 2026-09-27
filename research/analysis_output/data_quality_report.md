# Data Quality Report

## Database Overview
- **events**: 33,498 rows
- **market_data**: 73,145 rows
- **event_returns**: 937,944 rows

## Events Table Analysis
- **Date Coverage**: 2022-02-14 15:54:32.523000+00:00 to 2026-07-03 02:56:01.262000+00:00
- **Empty or Media-only Posts (no text)**: 8,307 posts
- **Missing Timestamps**: 0
- **Timezone Inconsistent (missing UTC offset)**: 0 posts

## Event Returns Analysis
- **Invalid VIX rows (asset='VIX')**: 33,498
- **Valid VIX rows (asset='^VIX')**: 33,498
- **Partial History (recent events)**: 14,996 rows
- **No Data Status**: 33,498 rows
- **Return Outliers (e.g. >50% daily or >100% weekly)**: 0 rows

## Asset Status Summary
Detailed counts exported to `analysis_output/asset_summary.csv`.