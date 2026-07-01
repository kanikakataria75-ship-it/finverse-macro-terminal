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
