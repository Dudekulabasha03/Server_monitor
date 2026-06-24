CREATE TABLE IF NOT EXISTS bios_history (
    id VARCHAR(36) PRIMARY KEY,
    server_id VARCHAR(36) REFERENCES servers(id) ON DELETE CASCADE,
    hostname VARCHAR(255),
    phase VARCHAR(16),
    bios_version VARCHAR(64),
    microcode VARCHAR(32),
    bmc_firmware VARCHAR(64),
    attributes JSON,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bios_history_server_id ON bios_history (server_id);
CREATE INDEX IF NOT EXISTS ix_bios_history_hostname ON bios_history (hostname);
CREATE INDEX IF NOT EXISTS ix_bios_history_phase ON bios_history (phase);
CREATE INDEX IF NOT EXISTS ix_bios_history_created ON bios_history (created_at);
CREATE INDEX IF NOT EXISTS ix_bios_hist_server_phase ON bios_history (server_id, phase, created_at);

-- Widen NIC speed so 100/1000 Mbps don't collapse to 0 Gbps
ALTER TABLE nics ALTER COLUMN speed_gbps TYPE double precision USING speed_gbps::double precision;
