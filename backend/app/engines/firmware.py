"""
Firmware Compliance Engine — compare installed vs approved baseline versions.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class FirmwareItem:
    component: str
    current: Optional[str]
    approved: Optional[str]
    compliant: bool


@dataclass
class FirmwareResult:
    compliant: bool
    items: List[FirmwareItem] = field(default_factory=list)
    outdated_count: int = 0


# Map server attribute -> baseline key
_FW_FIELDS = {
    "BIOS": "bios_version",
    "BMC": "bmc_firmware",
    "RAID": "raid_firmware",
    "NIC": "nic_firmware",
    "GPU": "gpu_firmware",
    "Storage": "storage_firmware",
}
_BASELINE_KEYS = {"BIOS": "bios", "BMC": "bmc", "RAID": "raid", "NIC": "nic", "GPU": "gpu", "Storage": "storage"}


class FirmwareCompliance:
    def evaluate(self, server) -> FirmwareResult:
        baseline = server.firmware_baseline or {}
        items: List[FirmwareItem] = []
        outdated = 0

        for label, attr in _FW_FIELDS.items():
            current = getattr(server, attr, None)
            approved = baseline.get(_BASELINE_KEYS[label])
            if current is None and approved is None:
                continue
            compliant = True
            if approved and current and str(current).strip() != str(approved).strip():
                compliant = False
                outdated += 1
            elif approved and not current:
                compliant = False
                outdated += 1
            items.append(FirmwareItem(label, current, approved, compliant))

        return FirmwareResult(compliant=(outdated == 0), items=items, outdated_count=outdated)
