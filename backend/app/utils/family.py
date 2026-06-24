"""
CPU-family detection for AMD EPYC servers.

Two entry points:
- derive_family(model_str): authoritative — maps a real BMC/Redfish model string
  (e.g. "AMD EPYC 9654 96-Core Processor") to a family. Used by the collector.
- family_from_codename(hostname): best-effort fallback from the AMD board codename
  embedded in the hostname (volcano/titanite/...). Used at import time before the
  BMC has been polled.

Important ambiguity: the EPYC 9004 (Genoa) and 9005 (Turin) generations BOTH use
4-digit 9xxx SKUs and Redfish model strings rarely carry the codename. The number
alone cannot tell Genoa from Turin/Bergamo, so for a bare 9xxx number with no
codename word we return None (unknown) rather than guess — that way the collector
never clobbers a correct codename-based import guess with a wrong one.
"""
from typing import Optional
import re

# Codename words that may appear directly in a model/marketing string (authoritative).
_CODENAME_WORDS = [
    ("turin", "Turin"),
    ("bergamo", "Bergamo"),
    ("genoa", "Genoa"),
    ("siena", "Siena"),
    ("sorano", "Sorano"),
    ("sorrento", "Sorano"),
    ("milan", "Milan"),
    ("rome", "Rome"),
    ("naples", "Naples"),
]

# AMD EPYC SKU numbering: a 4-digit number where the FIRST digit is the socket
# series (7/8/9) and the LAST digit is the generation:
#   7xx1 Naples, 7xx2 Rome, 7xx3 Milan,
#   9xx4 Genoa, 97x4 Bergamo, 8xx4 Siena,
#   9xx5 / 8xx5 Turin.
# Examples: 7763=Milan, 7302=Rome, 9654=Genoa, 9754=Bergamo, 8534=Siena, 9755=Turin.
_EPYC_SKU = re.compile(r"\b([789])(\d)(\d)(\d)[a-z]?\b")


def _family_from_sku(s: str):
    for m in _EPYC_SKU.finditer(s):
        series, d2, _d3, gen = m.group(1), m.group(2), m.group(3), m.group(4)
        if series == "7":
            return {"1": "Naples", "2": "Rome", "3": "Milan"}.get(gen)
        if series == "8":
            return {"4": "Siena", "5": "Turin"}.get(gen)
        if series == "9":
            if gen == "4":
                return "Bergamo" if d2 == "7" else "Genoa"
            if gen == "5":
                return "Turin"
    return None

# AMD board/platform codenames in hostnames → family (best-effort import fallback).
_HOSTNAME_CODENAME_FAMILY = [
    ("volcano", "Turin"),
    ("titanite", "Genoa"),
    ("cinnabar", "Genoa"),
    ("ruby", "Genoa"),
    ("shale", "Milan"),
    ("daytona", "Milan"),
]

KNOWN_FAMILIES = [
    "Naples", "Rome", "Milan", "Genoa", "Bergamo", "Siena", "Sorano", "Turin",
]


def derive_family(model_str: Optional[str]) -> Optional[str]:
    """Map a real CPU/system model string to an AMD EPYC family. None if unknown/ambiguous."""
    if not model_str:
        return None
    s = str(model_str).strip().lower()

    # 1) Explicit codename in the marketing string wins.
    for word, fam in _CODENAME_WORDS:
        if word in s:
            return fam

    # 2) EPYC SKU-number heuristic (first digit = series, last = generation).
    fam = _family_from_sku(s)
    if fam:
        return fam

    return None


def family_from_codename(hostname: Optional[str]) -> Optional[str]:
    """Best-effort family from the AMD board codename in a hostname. None if unknown."""
    if not hostname:
        return None
    h = str(hostname).strip().lower()
    for code, fam in _HOSTNAME_CODENAME_FAMILY:
        if code in h:
            return fam
    return None
