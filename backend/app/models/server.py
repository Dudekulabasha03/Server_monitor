from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Enum, Text, JSON,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class ServerStatus(str, enum.Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ServerVendor(str, enum.Enum):
    DELL = "dell"
    HPE = "hpe"
    LENOVO = "lenovo"
    SUPERMICRO = "supermicro"
    INSPUR = "inspur"
    CISCO = "cisco"
    QUANTA = "quanta"
    AMD_CRB = "amd_crb"
    OEM = "oem"
    UNKNOWN = "unknown"


class Server(Base):
    __tablename__ = "servers"

    id = Column(String(36), primary_key=True)  # UUID
    hostname = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255))
    fqdn = Column(String(512))

    # Network
    bmc_ip = Column(String(45), index=True)      # BMC/iDRAC/iLO IP
    bmc_port = Column(Integer, default=443)
    os_ip = Column(String(45))                    # OS management IP
    ipmi_ip = Column(String(45))

    # Identity
    vendor = Column(Enum(ServerVendor), default=ServerVendor.UNKNOWN)
    model = Column(String(255))
    serial_number = Column(String(128), unique=True, index=True)
    asset_tag = Column(String(128))
    service_tag = Column(String(128))

    # Location
    datacenter = Column(String(128), default="AMD-DC1")
    room = Column(String(64))
    row = Column(String(32))
    rack = Column(String(32), index=True)
    rack_unit = Column(Integer)
    rack_unit_size = Column(Integer, default=1)

    # Hardware Specs
    cpu_model = Column(String(255))
    family = Column(String(32), index=True)  # AMD EPYC family: Naples/Rome/Milan/Genoa/Bergamo/Siena/Sorano/Turin
    microcode = Column(String(32))           # primary-CPU microcode revision (e.g. 0xa101158)
    cpu_count = Column(Integer)
    cpu_cores_total = Column(Integer)
    cpu_threads_total = Column(Integer)
    memory_gb = Column(Integer)
    dimm_count = Column(Integer)
    gpu_count = Column(Integer, default=0)
    gpu_model = Column(String(255))

    # OS
    os_type = Column(String(64))     # linux | windows
    os_name = Column(String(128))
    os_version = Column(String(128))
    kernel_version = Column(String(128))

    # Firmware
    bmc_firmware = Column(String(64))
    bios_version = Column(String(64))
    raid_firmware = Column(String(64))
    nic_firmware = Column(String(64))
    gpu_firmware = Column(String(64))
    storage_firmware = Column(String(64))
    firmware_baseline_compliant = Column(Boolean, default=None)
    firmware_baseline = Column(JSON)  # {"bios": "2.18", "bmc": "...", ...} approved versions

    # Lifecycle
    procurement_date = Column(DateTime(timezone=True))
    installation_date = Column(DateTime(timezone=True))
    warranty_start = Column(DateTime(timezone=True))
    eol_date = Column(DateTime(timezone=True))   # End of Life
    eos_date = Column(DateTime(timezone=True))   # End of Support

    # Collection Config
    redfish_enabled = Column(Boolean, default=True)
    ipmi_enabled = Column(Boolean, default=True)
    os_agent_enabled = Column(Boolean, default=False)
    collect_interval = Column(Integer, default=60)  # seconds

    # Per-server BMC credentials (Vault remains the production path; these are a fallback)
    bmc_username = Column(String(64))
    bmc_password = Column(String(128))

    # Per-server OS/SSH credentials (for the OS-agent CPU/memory collector)
    os_username = Column(String(64))
    os_password = Column(String(128))

    # Status
    status = Column(Enum(ServerStatus), default=ServerStatus.UNKNOWN, index=True)
    health_score = Column(Float, default=None)
    last_seen = Column(DateTime(timezone=True))
    last_collection_at = Column(DateTime(timezone=True))
    collection_error = Column(Text)

    # Classification
    environment = Column(String(64), default="production")  # production | staging | dev | lab
    team = Column(String(128))
    project = Column(String(128))
    tags = Column(JSON, default=list)

    # Warranty
    warranty_expiry = Column(DateTime(timezone=True))
    support_contract = Column(String(128))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    discovered_at = Column(DateTime(timezone=True))

    # Relationships
    metrics_snapshots = relationship("MetricsSnapshot", back_populates="server", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="server", cascade="all, delete-orphan")
    health_scores = relationship("HealthScore", back_populates="server", cascade="all, delete-orphan")
    dimms = relationship("DimmSlot", back_populates="server", cascade="all, delete-orphan")
    disks = relationship("Disk", back_populates="server", cascade="all, delete-orphan")
    psus = relationship("PSU", back_populates="server", cascade="all, delete-orphan")
    nics = relationship("NIC", back_populates="server", cascade="all, delete-orphan")
    user_sessions = relationship("UserSession", back_populates="server", cascade="all, delete-orphan")
    risk_scores = relationship("RiskScore", back_populates="server", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="server", cascade="all, delete-orphan")
    availability_records = relationship("AvailabilityRecord", back_populates="server", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_server_status_health", "status", "health_score"),
        Index("ix_server_rack_location", "datacenter", "rack", "rack_unit"),
    )


class MetricsSnapshot(Base):
    """Latest snapshot of all metrics for a server (for fast dashboard queries)."""
    __tablename__ = "metrics_snapshots"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Thermal
    cpu_temp_avg = Column(Float)
    cpu_temp_max = Column(Float)
    inlet_temp = Column(Float)
    outlet_temp = Column(Float)
    dimm_temp_max = Column(Float)
    nvme_temp_max = Column(Float)
    gpu_temp_max = Column(Float)

    # CPU
    cpu_usage_avg = Column(Float)
    cpu_usage_max = Column(Float)
    load_avg_1m = Column(Float)
    load_avg_5m = Column(Float)
    load_avg_15m = Column(Float)

    # Memory
    memory_usage_pct = Column(Float)
    memory_used_gb = Column(Float)
    memory_free_gb = Column(Float)
    swap_usage_pct = Column(Float)

    # Power
    power_consumed_watts = Column(Float)
    power_capacity_watts = Column(Float)
    power_efficiency_pct = Column(Float)
    power_state = Column(String(32))  # On | Off | PoweringOn | PoweringOff

    # Storage
    disk_usage_avg_pct = Column(Float)
    disk_usage_max_pct = Column(Float)
    disk_io_read_mbps = Column(Float)
    disk_io_write_mbps = Column(Float)

    # Network
    net_rx_mbps = Column(Float)
    net_tx_mbps = Column(Float)
    net_errors_total = Column(Integer)
    net_drops_total = Column(Integer)

    # Fan
    fan_count = Column(Integer)
    fan_failed_count = Column(Integer)
    fan_speed_avg_rpm = Column(Integer)

    # PSU
    psu_count = Column(Integer)
    psu_failed_count = Column(Integer)

    # Utilization (from PIPT)
    util_bucket = Column(String(16), index=True)  # idle | light | active | heavy | unknown | off
    util_score = Column(Float)                     # 0-9 composite utilization

    # BMC-declared worst sensor health (OK | Warning | Critical)
    sensor_health = Column(String(16), index=True)

    # Full raw data (JSON for anything not in columns)
    raw_sensors = Column(JSON)

    server = relationship("Server", back_populates="metrics_snapshots")


class DimmSlot(Base):
    __tablename__ = "dimm_slots"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_name = Column(String(64), nullable=False)
    bank = Column(String(32))
    populated = Column(Boolean, default=False)
    capacity_gb = Column(Integer)
    speed_mhz = Column(Integer)
    manufacturer = Column(String(128))
    part_number = Column(String(128))
    serial_number = Column(String(128))
    dimm_type = Column(String(32))  # DDR4 | DDR5
    health = Column(String(32), default="OK")  # OK | Warning | Critical
    error_count = Column(Integer, default=0)

    server = relationship("Server", back_populates="dimms")

    __table_args__ = (UniqueConstraint("server_id", "slot_name"),)


class Disk(Base):
    __tablename__ = "disks"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    slot = Column(String(32))
    name = Column(String(128))
    disk_type = Column(String(32))   # SSD | HDD | NVMe
    capacity_gb = Column(Integer)
    model = Column(String(255))
    serial_number = Column(String(128))
    firmware_version = Column(String(64))
    protocol = Column(String(32))    # SATA | SAS | NVMe
    media_type = Column(String(32))  # HDD | SSD
    raid_member = Column(Boolean, default=False)
    raid_volume = Column(String(64))

    health = Column(String(32), default="OK")
    smart_status = Column(String(32))
    failure_predicted = Column(Boolean, default=False)
    failure_probability = Column(Float)  # ML output 0-1

    usage_pct = Column(Float)
    read_errors = Column(Integer, default=0)
    write_errors = Column(Integer, default=0)
    reallocated_sectors = Column(Integer, default=0)
    power_on_hours = Column(Integer)
    temperature_c = Column(Float)

    server = relationship("Server", back_populates="disks")


class PSU(Base):
    __tablename__ = "psus"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    slot = Column(String(32), nullable=False)
    model = Column(String(255))
    serial_number = Column(String(128))
    capacity_watts = Column(Integer)
    current_watts = Column(Float)
    voltage_v = Column(Float)
    current_amps = Column(Float)
    efficiency_rating = Column(String(32))  # 80Plus Platinum etc
    health = Column(String(32), default="OK")
    present = Column(Boolean, default=True)
    redundant = Column(Boolean, default=True)

    server = relationship("Server", back_populates="psus")

    __table_args__ = (UniqueConstraint("server_id", "slot"),)


class NIC(Base):
    __tablename__ = "nics"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64))
    mac_address = Column(String(17))
    speed_gbps = Column(Float)        # float so 100/1000 Mbps don't collapse to 0
    link_status = Column(String(32))  # canonical "Up" | "Down"
    ip_address = Column(String(45))
    driver = Column(String(128))
    firmware_version = Column(String(64))

    server = relationship("Server", back_populates="nics")
