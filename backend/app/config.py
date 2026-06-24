from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_NAME: str = "Helios"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://fleetmon:password@localhost:5432/fleetmon"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_STREAM_METRICS: str = "raw_metrics"
    REDIS_STREAM_ALERTS: str = "alerts_queue"
    REDIS_STREAM_EVENTS: str = "events_queue"

    # VictoriaMetrics
    VICTORIA_METRICS_URL: str = "http://localhost:8428"
    VICTORIA_METRICS_WRITE_URL: str = "http://localhost:8428/api/v1/import/prometheus"
    VICTORIA_METRICS_QUERY_URL: str = "http://localhost:8428/api/v1/query_range"

    # Collection Intervals (seconds)
    # BMC hardware telemetry changes slowly — poll Redfish/IPMI every 5 min to cut
    # datapoint volume ~5x. OS-agent stays frequent for live CPU/mem. Health/alerts
    # recompute every 2 min off the latest snapshots.
    COLLECT_INTERVAL_REDFISH: int = 300
    COLLECT_INTERVAL_IPMI: int = 300
    COLLECT_INTERVAL_OS_AGENT: int = 120
    COLLECT_INTERVAL_HEALTH_SCORE: int = 120
    DISCOVERY_SCAN_INTERVAL: int = 3600
    EVALUATE_ALERTS_INTERVAL: int = 120

    # Autonomous SEL triage (Tier-2: reversible actions only)
    SEL_AUTOTRIAGE_ENABLED: bool = True       # master on/off for the loop
    SEL_AUTOTRIAGE_SHADOW: bool = True        # True = classify+log only, take NO action
    SEL_AUTOTRIAGE_INTERVAL: int = 600        # seconds between triage sweeps
    AUTONOMY_PAUSED: bool = False             # global kill switch for ALL autonomous actions

    # Redfish
    REDFISH_TIMEOUT: int = 30
    REDFISH_MAX_RETRIES: int = 3
    REDFISH_CONCURRENT_LIMIT: int = 50

    # IPMI
    IPMI_TIMEOUT: int = 10
    IPMI_MAX_RETRIES: int = 2

    # OS Agent (SSH CPU/memory collection) — batches of 5, every 20s
    OS_AGENT_CONCURRENT_LIMIT: int = 5
    OS_AGENT_CONNECT_TIMEOUT: int = 6
    OS_AGENT_PORT_CHECK_TIMEOUT: int = 2

    # Auth (Azure AD / Keycloak)
    AUTH_PROVIDER: str = "azure_ad"  # azure_ad | keycloak | local
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    KEYCLOAK_URL: str = ""
    KEYCLOAK_REALM: str = "fleet-monitor"

    # RBAC JWT (local auth)
    JWT_SECRET_KEY: str = "change-me-jwt-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # RBAC Bootstrap (super admin seeded on first run)
    RBAC_ENABLED: bool = False
    RBAC_SUPER_ADMIN_EMAIL: str = "admin@amd.com"
    RBAC_SUPER_ADMIN_PASSWORD: str = "ChangeMe123!"
    RBAC_SUPER_ADMIN_NAME: str = "System Administrator"

    # HashiCorp Vault
    VAULT_URL: str = "http://localhost:8200"
    VAULT_TOKEN: str = ""
    VAULT_SECRET_PATH: str = "secret/fleet-monitor"

    # Alerting
    SMTP_HOST: str = "smtp.amd.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "fleet-monitor@amd.com"
    TEAMS_WEBHOOK_URL: str = ""
    SLACK_BOT_TOKEN: str = ""
    SLACK_CHANNEL: str = "#server-alerts"

    # PRISM OS-Provisioning API (hardware info + OS IP discovery)
    PRISM_ENABLED: bool = False
    PRISM_URL: str = "https://prism.amd.com/os-provisioning-api"
    PRISM_USER: str = ""
    PRISM_PASSWORD: str = ""
    PRISM_API_KEY: str = ""

    # PIPT dashboard API (BMC telemetry: watts, cpu_watts, fans, temps, SEL — 136 hosts)
    PIPT_ENABLED: bool = False
    PIPT_URL: str = "http://tsp-dogmatix-blr.amd.com:8787"
    PIPT_INTERVAL: int = 180  # seconds
    SNAPSHOT_RETENTION_HOURS: int = 48  # delete raw snapshots older than this

    # ── External BIOS API server ─────────────────────────────────────────────
    BIOS_API_URL: str = "http://localhost:5000"   # override with BIOS_API_URL env var

    # ── AI / Agentic layer (GPT-oss-20B on-prem, experimental) ──────────────
    AI_ENABLED: bool = False
    AI_BASE_URL: str = "https://llm-api.amd.com/api/v1"
    AI_MODEL: str = "Claude-Opus-4.6"
    AI_SUBSCRIPTION_KEY: str = ""   # Ocp-Apim-Subscription-Key header
    AI_TIMEOUT: int = 60
    AI_MAX_TOKENS: int = 6000
    AI_TEMPERATURE: float = 0.2
    AI_MAX_REACT_STEPS: int = 5

    # Health Score Weights
    HEALTH_WEIGHT_HARDWARE: float = 0.30
    HEALTH_WEIGHT_THERMAL: float = 0.20
    HEALTH_WEIGHT_POWER: float = 0.10
    HEALTH_WEIGHT_STORAGE: float = 0.15
    HEALTH_WEIGHT_NETWORK: float = 0.10
    HEALTH_WEIGHT_UTILIZATION: float = 0.15

    # Thresholds
    TEMP_CPU_WARNING: float = 75.0
    TEMP_CPU_CRITICAL: float = 85.0
    TEMP_INLET_WARNING: float = 30.0
    TEMP_INLET_CRITICAL: float = 35.0
    CPU_USAGE_WARNING: float = 80.0
    CPU_USAGE_CRITICAL: float = 95.0
    MEM_USAGE_WARNING: float = 85.0
    MEM_USAGE_CRITICAL: float = 95.0
    DISK_USAGE_WARNING: float = 80.0
    DISK_USAGE_CRITICAL: float = 90.0
    POWER_HEADROOM_WARNING: float = 0.85  # 85% of PSU capacity


settings = Settings()
