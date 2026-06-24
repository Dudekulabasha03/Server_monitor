CREATE TABLE IF NOT EXISTS triage_logs (
    id VARCHAR(36) PRIMARY KEY,
    event_key VARCHAR(255) NOT NULL UNIQUE,
    server_id VARCHAR(36) REFERENCES servers(id) ON DELETE CASCADE,
    hostname VARCHAR(255),
    severity VARCHAR(16),
    message VARCHAR(1024),
    verdict VARCHAR(16),
    confidence DOUBLE PRECISION,
    reasoning VARCHAR(2048),
    action_taken VARCHAR(32),
    shadow BOOLEAN DEFAULT TRUE,
    alert_id VARCHAR(36),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_triage_logs_event_key ON triage_logs (event_key);
CREATE INDEX IF NOT EXISTS ix_triage_logs_server_id ON triage_logs (server_id);
CREATE INDEX IF NOT EXISTS ix_triage_logs_hostname ON triage_logs (hostname);
CREATE INDEX IF NOT EXISTS ix_triage_logs_verdict ON triage_logs (verdict);
CREATE INDEX IF NOT EXISTS ix_triage_created ON triage_logs (created_at);
CREATE INDEX IF NOT EXISTS ix_triage_verdict_created ON triage_logs (verdict, created_at);
