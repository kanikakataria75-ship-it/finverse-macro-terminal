-- Finverse Macro Engine Database Schema

CREATE TABLE IF NOT EXISTS master_country_states (
    country_iso VARCHAR(3) PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    war_intensity_score NUMERIC(5,2) DEFAULT 0.00,
    oil_reserves_barrels BIGINT DEFAULT 0,
    gold_reserves_tonnes NUMERIC(10,2) DEFAULT 0.00,
    composite_risk_score NUMERIC(5,2) DEFAULT 0.00,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    macro_metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS country_macro_history (
    log_id SERIAL PRIMARY KEY,
    country_iso VARCHAR(3) REFERENCES master_country_states(country_iso) ON DELETE CASCADE,
    metric_name VARCHAR(50) NOT NULL,
    metric_value NUMERIC NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger Function for Historical Snapshots
CREATE OR REPLACE FUNCTION log_macro_history()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.war_intensity_score IS DISTINCT FROM OLD.war_intensity_score THEN
        INSERT INTO country_macro_history (country_iso, metric_name, metric_value)
        VALUES (NEW.country_iso, 'war_intensity_score', NEW.war_intensity_score);
    END IF;

    IF NEW.oil_reserves_barrels IS DISTINCT FROM OLD.oil_reserves_barrels THEN
        INSERT INTO country_macro_history (country_iso, metric_name, metric_value)
        VALUES (NEW.country_iso, 'oil_reserves_barrels', NEW.oil_reserves_barrels);
    END IF;

    IF NEW.gold_reserves_tonnes IS DISTINCT FROM OLD.gold_reserves_tonnes THEN
        INSERT INTO country_macro_history (country_iso, metric_name, metric_value)
        VALUES (NEW.country_iso, 'gold_reserves_tonnes', NEW.gold_reserves_tonnes);
    END IF;

    IF NEW.composite_risk_score IS DISTINCT FROM OLD.composite_risk_score THEN
        INSERT INTO country_macro_history (country_iso, metric_name, metric_value)
        VALUES (NEW.country_iso, 'composite_risk_score', NEW.composite_risk_score);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists to allow safe re-runs
DROP TRIGGER IF EXISTS trg_log_macro_history ON master_country_states;

-- Attach Trigger to Table A
CREATE TRIGGER trg_log_macro_history
AFTER UPDATE ON master_country_states
FOR EACH ROW
EXECUTE FUNCTION log_macro_history();

-- --------------------------------------------------------
-- NEW: FINANCIAL ASSETS & TIME SERIES ENGINE
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS master_financial_assets (
    ticker_symbol VARCHAR(20) PRIMARY KEY,
    asset_name VARCHAR(100) NOT NULL,
    general_analysis TEXT,
    support_level NUMERIC(12, 2),
    resistance_level NUMERIC(12, 2),
    fas_score VARCHAR(10) DEFAULT 'N/A',
    sectoral_dynamics JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_mfa_asset_name ON master_financial_assets (asset_name);
CREATE INDEX IF NOT EXISTS idx_mfa_ticker ON master_financial_assets (ticker_symbol);

CREATE TABLE IF NOT EXISTS asset_price_history (
    log_id SERIAL PRIMARY KEY,
    ticker_symbol VARCHAR(20) REFERENCES master_financial_assets(ticker_symbol) ON DELETE CASCADE,
    price_close NUMERIC(12, 2) NOT NULL,
    volume BIGINT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_aph_ticker_time ON asset_price_history (ticker_symbol, recorded_at);

-- Mock Data Insertion for Testing Search & Chart
INSERT INTO master_financial_assets (ticker_symbol, asset_name, general_analysis, support_level, resistance_level, fas_score)
VALUES 
('NIFTY50', 'Nifty 50 Index', 'Top 50 Indian companies', 23000.00, 24500.00, 'STRONG'),
('BTCUSD', 'Bitcoin to USD', 'Leading cryptocurrency', 55000.00, 65000.00, 'VOLATILE'),
('RELIANCE', 'Reliance Industries Ltd', 'Indian conglomerate', 2800.00, 3100.00, 'STABLE'),
('AAPL', 'Apple Inc.', 'Consumer electronics giant', 160.00, 190.00, 'STABLE'),
('NVDA', 'NVIDIA Corporation', 'AI hardware leader', 100.00, 140.00, 'STRONG')
ON CONFLICT (ticker_symbol) DO NOTHING;

-- Mock Time Series Data for NIFTY50
INSERT INTO asset_price_history (ticker_symbol, price_close, volume, recorded_at)
SELECT 'NIFTY50', 
       24000.00 + (random() * 200 - 100), 
       (random() * 1000000)::bigint, 
       CURRENT_TIMESTAMP - (i || ' hours')::interval
FROM generate_series(1, 48) i
ON CONFLICT DO NOTHING;

-- Mock Time Series Data for BTCUSD
INSERT INTO asset_price_history (ticker_symbol, price_close, volume, recorded_at)
SELECT 'BTCUSD', 
       60000.00 + (random() * 1000 - 500), 
       (random() * 5000)::bigint, 
       CURRENT_TIMESTAMP - (i || ' hours')::interval
FROM generate_series(1, 48) i
ON CONFLICT DO NOTHING;
