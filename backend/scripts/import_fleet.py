"""
Bulk-import the full Security Patch Team fleet.

Run: docker compose run --rm backend python -m scripts.import_fleet

- Normalizes irregular hostnames and DNS-resolves the BMC IP.
- Upserts by hostname (existing servers updated, new ones inserted).
- Sets per-server BMC credentials (Milan=ADMIN/ADMIN, others=root/0penBmc).
- Maps region->datacenter, family->model/cpu_model/tag, assigns rack/U.
- Prints a computation summary (resolved/unresolved + per family/region tallies).
"""
import asyncio
import socket
import uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.server import Server, ServerVendor, ServerStatus

ROOT = ("root", "0penBmc")
ADMIN = ("ADMIN", "ADMIN")

# (raw_name, region, family, creds)
ROSTER = []

def _add(names, region, family, creds):
    for n in names:
        ROSTER.append((n, region, family, creds))

# ---- MILAN (ADMIN/ADMIN) ----
_add(["Daytonax7D90","DaytonaxAda2","Daytonax15E6","Daytonax7E8E","Daytonax174F","Daytonax15A4",
      "Daytonax1659","Daytonax15CB","Daytonax7DDC","Daytonax1759","Daytonax162D","Daytonax16b1",
      "Daytonax15AC","Daytonax1722","DaytonaxFE17","Daytonax16A3","Daytonax156D","Daytonax1791",
      "Daytonax06DF","DaytonaxADA4"], "Santa Clara", "Milan", ADMIN)
_add(["daytonax426f","daytonax42cd","daytonax42cf","daytonax42ef","daytonax4367","daytonax437d",
      "daytonax60b5","daytonax60b9","daytonax60bd","daytonax60bf","daytonax60c5","daytonax60d5",
      "daytonax60f3","daytonax6107","daytonax610f","daytonax6133","daytonax615d","daytonax617b",
      "daytonax7e42","daytonaxd414"], "Dallas", "Milan", ADMIN)

# ---- GENOA (root/0penBmc) ----
_add(["titanite35fc","titanited5ba","titanite1997","titanite1965","titanite1aa1","titanite1a3b",
      "titanite1634","titanite1a71","titanite1a69","titanite1618","titanite1a79","titanited3ec",
      "titanite165c","titanite17bc","titanite18b6","titanited558","titanite35dc","titanite35ee",
      "titanited442","titanited62e"], "Santa Clara", "Genoa", ROOT)
_add(["titanite-1886","titanite-189e","titanite-34c0","titanite-9bc7","titanite-d2fe","titanite-d310",
      "titanite-d39c","titanite-d3c8","titanite-d4c0","titanite-d51a","titanite-d51e","titanite-d520",
      "titanite-d534","titanite-d560","titanite-d59c","titanite-d5aa","titanite-d620","titanite-d66e"],
     "Plano", "Genoa", ROOT)

# ---- TURIN CLASSIC (root/0penBmc) ----
_add(["Volcano-A990","Volcano-9CBE","Volcano-9F0A","Volcano-9D16","Volcano-9E7A","Volcano-9D82",
      "Volcano-9C4C","Volcano-5CE7","Volcano-5867","Volcano-6077"], "Santa Clara", "Turin Classic", ROOT)
_add(["VOLCANOEBF3","VOLCANOEBFD","VOLCANOEC15","VOLCANOEC2F","VOLCANOEC61","VOLCANOEC69","VOLCANOEC79",
      "VOLCANOECA1","VOLCANOECE7","VOLCANOECF3","VOLCANOED1F","VOLCANOED6D","VOLCANOEDA7","VOLCANOEDDD",
      "VOLCANOEE2D","VOLCANOEE55","VOLCANOEED3","VOLCANOEEE3","VOLCANOEF0D","VOLCANOEF17"],
     "Plano", "Turin Classic", ROOT)

# ---- TURIN DENSE (root/0penBmc) ----
_add(["Volcano-AB6C","Volcano-9A7A","Volcano-9C06","Volcano-9D88","Volcano-9FFC","Volcano-9E18",
      "Volcano-9A84","Volcano-9AF0","Volcano-5FC3","Volcano-EF05"], "Santa Clara", "Turin Dense", ROOT)
_add(["VOLCANOE92D","VOLCANOE939","VOLCANOE9B9","VOLCANOE9BD","VOLCANOEA2B","VOLCANOEA7F","VOLCANOEA8F",
      "VOLCANOEA9D","VOLCANOEAB9","VOLCANOEAFD","VOLCANOEB3B","VOLCANOEB47","VOLCANOEB83","VOLCANOEB87",
      "VOLCANOEB8B","VOLCANOEB8D","VOLCANOEB9B","VOLCANOEBA5","VOLCANOEBDD","VOLCANOEBF1"],
     "Plano", "Turin Dense", ROOT)

FAMILY_MODEL = {
    "Milan": "AMD EPYC 7003 (Milan)",
    "Genoa": "AMD EPYC 9004 (Genoa)",
    "Turin Classic": "AMD EPYC 9005 (Turin Classic)",
    "Turin Dense": "AMD EPYC 9005 (Turin Dense)",
}


def _candidates(raw: str):
    """Generate candidate FQDN-local hostnames to resolve, in priority order."""
    low = raw.lower()
    compact = low.replace("-", "")
    cands = [low, compact]
    for p in ("daytonax", "titanite", "volcano"):
        if compact.startswith(p):
            rest = compact[len(p):]
            cands.append(f"{p}-{rest}")
    # dedupe preserve order
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def _resolve(raw: str):
    """Return (hostname, fqdn, ip) for first resolving candidate, else (best_name, fqdn, None)."""
    for cand in _candidates(raw):
        fqdn = f"{cand}.amd.com"
        try:
            ip = socket.gethostbyname(fqdn)
            return cand, fqdn, ip
        except Exception:
            continue
    # fallback: canonical guess (dash form if titanite/volcano, compact for daytona)
    low = raw.lower().replace("-", "")
    best = low
    for p in ("titanite", "volcano"):
        if low.startswith(p):
            best = f"{p}-{low[len(p):]}"
    return best, f"{best}.amd.com", None


async def main():
    resolved = 0
    unresolved = 0
    inserted = 0
    updated = 0
    by_family = {}
    by_region = {}

    async with AsyncSessionLocal() as db:
        existing = {s.hostname: s for s in (await db.execute(select(Server))).scalars().all()}

        # rack assignment counters per (region, family)
        rack_counter = {}

        for raw, region, family, (user, pw) in ROSTER:
            hostname, fqdn, ip = _resolve(raw)
            if ip:
                resolved += 1
            else:
                unresolved += 1
            by_family[family] = by_family.get(family, 0) + 1
            by_region[region] = by_region.get(region, 0) + 1

            rack_key = f"{region[:2].upper()}-{family.split()[-1][:3].upper()}"
            n = rack_counter.get(rack_key, 0) + 1
            rack_counter[rack_key] = n

            srv = existing.get(hostname)
            if srv is None:
                srv = Server(id=str(uuid.uuid4()), hostname=hostname)
                db.add(srv)
                inserted += 1
            else:
                updated += 1

            srv.fqdn = fqdn
            srv.bmc_ip = ip or srv.bmc_ip
            srv.vendor = ServerVendor.AMD_CRB
            srv.model = FAMILY_MODEL.get(family, family)
            srv.cpu_model = FAMILY_MODEL.get(family, family)
            srv.datacenter = region
            srv.rack = rack_key
            srv.rack_unit = ((n - 1) % 42) + 1
            srv.environment = "production"
            srv.team = "Security Patch Team"
            srv.tags = [family, region]
            srv.bmc_username = user
            srv.bmc_password = pw
            srv.redfish_enabled = bool(ip)
            srv.ipmi_enabled = False
            if not ip:
                srv.status = ServerStatus.UNKNOWN
                srv.collection_error = "DNS unresolved at import"

        await db.commit()

    print("=" * 56)
    print("FLEET IMPORT SUMMARY")
    print("=" * 56)
    print(f"Total in roster : {len(ROSTER)}")
    print(f"Resolved (DNS)  : {resolved}")
    print(f"Unresolved      : {unresolved}")
    print(f"Inserted        : {inserted}")
    print(f"Updated         : {updated}")
    print("-" * 56)
    print("By family :", by_family)
    print("By region :", by_region)
    print("=" * 56)


if __name__ == "__main__":
    asyncio.run(main())
