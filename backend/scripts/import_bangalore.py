"""
Bulk-import the Bangalore / TSP fleet (~140 mixed-vendor BMC servers).

Run: docker compose run --rm backend python -m scripts.import_bangalore

- Parses the embedded RAW table of "https://<bmc-host>  <user>/<password>" rows.
- region/datacenter = "Bangalore", team = "TSP", tags = ["Bangalore", "TSP"].
- Vendor inferred from hostname prefix (idrac/ilo/smc/xcc/daytona/AMD codenames).
- Family is a best-effort guess from the hostname codename at import time; the
  Redfish collector overwrites it with the real BMC model on the first poll.
- Per-server BMC creds stored on the row (CredentialProvider reads them first).
- Upserts by hostname (re-runnable, no duplicates). DNS-resolves the BMC IP.
"""
import asyncio
import socket
import uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.server import Server, ServerVendor, ServerStatus
from app.utils.family import family_from_codename

REGION = "Bangalore"
TEAM = "TSP"

# Raw rows exactly as provided. Format: "<bmc-url>\t<user>/<password>".
RAW = """
https://idrac-bv4j2g3.amd.com	root/calvin
https://idrac-f8v3mh3.amd.com	root/calvin
https://ilomxq02203pc.amd.com	root/amd1234!
https://idrac-fbc5pt3.amd.com	root/amd1234!
https://idrac-dnnwms3.amd.com	root/calvin
https://idrac-fnnwms3.amd.com	root/calvin
https://ilosgh302vjp9.amd.com	root/amd1234!
https://ilosgh302vjpm.amd.com	root/amd1234!
https://idrac-jpn43w2.amd.com	root/amd1234!
https://idrac-jpn53w2.amd.com	root/amd1234!
https://idrac-jpn60w2.amd.com	root/amd1234!
https://idrac-jpn70w2.amd.com	root/amd1234!
https://idrac-3zmlh13.amd.com	root/calvin
https://ilomxq82906hb.amd.com	root/amd1234!
https://ilomxq84006h4.amd.com	root/amd1234!
https://ilomxq93400n7.amd.com	root/amd1234!
https://ilomxq93400nf.amd.com	root/amd1234!
https://ilomxq02203pf.amd.com	root/amd1234!
https://ilomxq02203pt.amd.com	root/amd1234!
https://ilocn70461j1x.amd.com	root/amd1234!
https://ilocn704716q9.amd.com	root/amd1234!
https://ilo2m292201qw.amd.com	root/amd1234!
https://ilo2m2030082z.amd.com	root/amd1234!
https://ilo2m281607l5.amd.com	root/amd1234!
https://ilocn70381lhd.amd.com	root/amd1234!
https://smc3162-ipmi.amd.com	root/amd1234!
https://smc00962-ipmi.amd.com	root/amd1234!
https://smc00958-ipmi.amd.com	root/amd1234!
https://smc00957-ipmi.amd.com	root/amd1234!
https://smc2890-ipmi.amd.com	root/amd1234!
https://idrac-1gw9ny3.amd.com	root/amd1234!
https://XCC-7D9A-J900RHDL.amd.com	root/amd1234!
https://XCC-7D9A-J900T0E1.amd.com	root/amd1234!
https://ilosgh343n4s7.amd.com	root/amd1234!
https://ilosgh343n4sd.amd.com	root/amd1234!
https://smc0169-ipmi.amd.com	ADMIN/amd1234!
https://smc0170-ipmi.amd.com	ADMIN/amd1234!
https://DaytonaxADBE.amd.com	ADMIN/ADMIN
https://Daytonax15BA.amd.com	ADMIN/ADMIN
https://Daytonax15AA.amd.com	ADMIN/ADMIN
https://Daytonax1796.amd.com	ADMIN/ADMIN
https://DaytonaxDE58.amd.com	ADMIN/ADMIN
https://Daytonax16BA.amd.com	ADMIN/ADMIN
https://Daytonax16E8.amd.com	ADMIN/ADMIN
https://DaytonaxAD22.amd.com	ADMIN/ADMIN
https://Daytonax16B5.amd.com	ADMIN/ADMIN
https://Daytonax1682.amd.com	ADMIN/ADMIN
https://DaytonaxDE4E.amd.com	ADMIN/ADMIN
https://cinnabar-309f.amd.com	root/0penBmc
https://cinnabar-3f5a.amd.com	root/0penBmc
https://cinnabar-3f3e.amd.com	root/0penBmc
https://Cinnabar-3f04.amd.com	root/0penBmc
https://Cinnabar-3eb0.amd.com	root/0penBmc
https://Cinnabar-3f6e.amd.com	root/0penBmc
https://Cinnabar-3ede.amd.com	root/0penBmc
https://Cinnabar-3e92.amd.com	root/0penBmc
https://volcano-5e33.amd.com	root/0penBmc
https://volcano-6307.amd.com	root/0penBmc
https://volcano-5373.amd.com	root/0penBmc
https://volcano-5a1f.amd.com	root/0penBmc
https://volcano-598f.amd.com	root/0penBmc
https://volcano-5cb3.amd.com	root/0penBmc
https://volcano-624b.amd.com	root/0penBmc
https://volcano-626f.amd.com	root/0penBmc
https://volcano-5caf.amd.com	root/0penBmc
https://volcano-52df.amd.com	root/0penBmc
https://volcano-58a7.amd.com	root/0penBmc
https://volcano-5853.amd.com	root/0penBmc
https://volcano-5913.amd.com	root/0penBmc
https://shale-27CA.amd.com	root/0penBmc
https://shale-261C.amd.com	root/0penBmc
https://shale-74CE.amd.com	root/0penBmc
https://shale-74d0.amd.com	root/0penBmc
https://cinnabar-3041.amd.com	root/0penBmc
https://cinnabar-3161.amd.com	root/0penBmc
https://cinnabar-3073.amd.com	ADMIN/ADMIN
https://cinnabar-30bb.amd.com	root/0penBmc
https://Daytonax171E.amd.com	root/0penBmc
https://cinnabar-3ee2.amd.com	root/0penBmc
https://Titanite-D32A.amd.com	root/0penBmc
https://Titanite-D33E.amd.com	root/0penBmc
https://Titanite-D3D0.amd.com	root/0penBmc
https://Titanite-1A03.amd.com	root/0penBmc
https://Titanite-D58A.amd.com	root/0penBmc
https://Titanite-19CD.amd.com	root/0penBmc
https://Titanite-D5F8.amd.com	root/0penBmc
https://Titanite-D67E.amd.com	root/0penBmc
https://Titanite-D68C.amd.com	root/0penBmc
https://Titanite-D57C.amd.com	root/0penBmc
https://Titanite-D2EA.amd.com	root/0penBmc
https://Titanite-D672.amd.com	root/0penBmc
https://Titanite-1A41.amd.com	root/0penBmc
https://Titanite-D2E6.amd.com	root/0penBmc
https://Titanite-D3B4.amd.com	root/0penBmc
https://Titanite-D684.amd.com	root/0penBmc
https://Titanite-D430.amd.com	root/0penBmc
https://Titanite-1A97.amd.com	root/0penBmc
https://titanite-D5CA.amd.com	root/0penBmc
https://titanite-D364.amd.com	root/0penBmc
https://titanite-D330.amd.com	root/0penBmc
https://titanite-D692.amd.com	root/0penBmc
https://volcano-9ce2.amd.com	root/0penBmc
https://volcano-9aaa.amd.com	root/0penBmc
https://volcano-9d18.amd.com	root/0penBmc
https://volcano-9b70.amd.com	root/0penBmc
https://volcano-9a12.amd.com	root/0penBmc
https://volcano-9aa0.amd.com	root/0penBmc
https://volcano-9f92.amd.com	root/0penBmc
https://volcano-a082.amd.com	root/0penBmc
https://volcano-9f18.amd.com	root/0penBmc
https://volcano-9f2c.amd.com	root/0penBmc
https://volcano-9b44.amd.com	root/0penBmc
https://volcano-9fee.amd.com	root/0penBmc
https://volcano-9a52.amd.com	root/0penBmc
https://volcano-9a04.amd.com	root/0penBmc
https://volcano-9d60.amd.com	root/0penBmc
https://volcano-a05e.amd.com	root/0penBmc
https://volcano-9edc.amd.com	root/0penBmc
https://volcano-9a44.amd.com	root/0penBmc
https://ruby-9707.amd.com	root/0penBmc
https://ruby-961d.amd.com	root/0penBmc
https://ruby-DDE5.amd.com	root/0penBmc
https://ruby-9629.amd.com	root/0penBmc
https://ruby-9565.amd.com	root/0penBmc
https://ruby-9719.amd.com	root/0penBmc
https://volcano-aaa0.amd.com	root/0penBmc
https://volcano-a08e.amd.com	root/0penBmc
https://volcano-aa34.amd.com	root/0penBmc
https://volcano-aa1e.amd.com	root/0penBmc
https://cinnabar-0311.amd.com	root/0penBmc
https://cinnabar-0359.amd.com	root/0penBmc
https://cinnabar-034d.amd.com	root/0penBmc
https://cinnabar-032f.amd.com	root/0penBmc
https://cinnabar-0345.amd.com	root/0penBmc
https://cinnabar-033d.amd.com	root/0penBmc
https://cinnabar-0313.amd.com	root/0penBmc
"""


def _vendor_for(host: str) -> ServerVendor:
    h = host.lower()
    if h.startswith("idrac"):
        return ServerVendor.DELL
    if h.startswith("ilo"):
        return ServerVendor.HPE
    if h.startswith("smc") or "-ipmi" in h:
        return ServerVendor.SUPERMICRO
    if h.startswith("xcc"):
        return ServerVendor.LENOVO
    if h.startswith("daytona"):
        return ServerVendor.AMD_CRB
    # AMD OpenBMC codename boards
    if any(h.startswith(p) for p in ("volcano", "titanite", "cinnabar", "ruby", "shale")):
        return ServerVendor.AMD_CRB
    return ServerVendor.UNKNOWN


def _parse_rows():
    """Return list of (hostname_label, fqdn, user, password) from RAW."""
    out = []
    seen = set()
    for line in RAW.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # split host and cred on whitespace (tab or spaces)
        parts = line.split()
        url, cred = parts[0], parts[1]
        host = url.replace("https://", "").replace("http://", "").strip().rstrip("/")
        fqdn = host
        label = host.split(".")[0].lower()  # hostname without domain, normalized
        user, _, pw = cred.partition("/")
        if label in seen:
            continue
        seen.add(label)
        out.append((label, fqdn, user, pw))
    return out


def _resolve(fqdn: str):
    try:
        return socket.gethostbyname(fqdn)
    except Exception:
        return None


async def main():
    rows = _parse_rows()
    inserted = updated = resolved = unresolved = 0
    by_family = {}

    async with AsyncSessionLocal() as db:
        existing = {s.hostname: s for s in (await db.execute(select(Server))).scalars().all()}

        for label, fqdn, user, pw in rows:
            ip = _resolve(fqdn)
            if ip:
                resolved += 1
            else:
                unresolved += 1

            fam = family_from_codename(label)
            by_family[fam or "Unknown"] = by_family.get(fam or "Unknown", 0) + 1

            srv = existing.get(label)
            if srv is None:
                srv = Server(id=str(uuid.uuid4()), hostname=label)
                db.add(srv)
                existing[label] = srv
                inserted += 1
            else:
                updated += 1

            srv.fqdn = fqdn
            srv.bmc_ip = ip or srv.bmc_ip
            srv.vendor = _vendor_for(label)
            srv.datacenter = REGION
            srv.team = TEAM
            srv.tags = [REGION, TEAM]
            srv.environment = "production"
            srv.bmc_username = user
            srv.bmc_password = pw
            srv.redfish_enabled = bool(ip)
            srv.ipmi_enabled = False
            if fam and not srv.family:
                srv.family = fam  # best-effort; collector overwrites from real model
            if not ip:
                srv.status = ServerStatus.UNKNOWN
                srv.collection_error = "DNS unresolved at import"

        await db.commit()

    print("=" * 56)
    print("BANGALORE / TSP IMPORT SUMMARY")
    print("=" * 56)
    print(f"Rows parsed     : {len(rows)}")
    print(f"Resolved (DNS)  : {resolved}")
    print(f"Unresolved      : {unresolved}")
    print(f"Inserted        : {inserted}")
    print(f"Updated         : {updated}")
    print("By family guess :", by_family)
    print("=" * 56)


if __name__ == "__main__":
    asyncio.run(main())
