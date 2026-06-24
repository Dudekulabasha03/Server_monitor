#!/bin/bash
# health-check.sh — Verify both DEV and PROD stacks
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[1;33m"; NC="\033[0m"

ok() { echo -e "  ${GREEN}[OK]${NC}  $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }

check_http() {
  local label=$1 url=$2
  local code=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
  [ "$code" = "200" ] && ok "$label (HTTP $code)" || fail "$label (HTTP $code)"
}
check_health() {
  local label=$1 url=$2
  local status=$(curl -s --max-time 5 "$url" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  [ "$status" = "ok" ] && ok "$label" || fail "$label ($status)"
}

echo -e "${YELLOW}=== Helios Health Check — $(date) ===${NC}"
echo ""
echo -e "${YELLOW}DEV stack (3100/8100):${NC}"
check_health "DEV Backend"   "http://localhost:8100/health"
check_http   "DEV Frontend"  "http://localhost:3100/"
check_http   "DEV Auth"      "http://localhost:8100/auth/teams"

echo ""
echo -e "${YELLOW}PROD stack (3200/8200):${NC}"
check_health "PROD Backend"  "http://localhost:8200/health"
check_http   "PROD Frontend" "http://localhost:3200/"
check_http   "PROD Auth"     "http://localhost:8200/auth/teams"

echo ""
echo -e "${YELLOW}Infrastructure:${NC}"
REDIS=$(docker exec fleetmon-redis redis-cli ping 2>/dev/null)
[ "$REDIS" = "PONG" ] && ok "Redis" || fail "Redis"
PGPROD=$(docker exec fleetmon-postgres pg_isready -U fleetmon 2>/dev/null | grep -c "accepting")
[ "$PGPROD" = "1" ] && ok "Postgres (prod)" || fail "Postgres (prod)"
check_health "VictoriaMetrics" "http://localhost:8428/health"

echo ""
echo -e "${YELLOW}Fleet data:${NC}"
SUMMARY=$(curl -s http://localhost:8200/api/v1/servers/summary 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"total={d.get('total')} healthy={d.get('healthy')} warning={d.get('warning')} critical={d.get('critical')}\")" 2>/dev/null)
ok "Fleet: $SUMMARY"

echo ""
echo -e "${YELLOW}Source parity (DEV vs PROD):${NC}"
FE_DIFFS=$(diff -rq --exclude="*.pyc" --exclude="__pycache__" --exclude=".next" --exclude="node_modules" \
  /home/amd/fleet-monitor/frontend/src /home/amd/helios-rbac/frontend/src 2>/dev/null | wc -l)
BE_DIFFS=$(diff -rq --exclude="*.pyc" --exclude="__pycache__" \
  /home/amd/fleet-monitor/backend/app /home/amd/helios-rbac/backend/app 2>/dev/null | \
  grep -v "core\|auth\|admin\|reserv\|superadmin\|export" | wc -l)
[ "$FE_DIFFS" = "0" ] && ok "Frontend in sync" || warn "Frontend: $FE_DIFFS file(s) differ (run promote.sh)"
[ "$BE_DIFFS" = "0" ] && ok "Backend in sync"  || warn "Backend:  $BE_DIFFS file(s) differ (run promote.sh)"
