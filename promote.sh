#!/bin/bash
# promote.sh — Promote DEV (3100) to PROD (3200)
# Usage: ./promote.sh [--force]
set -e
FORCE=${1:-""}
DEV=/home/amd/fleet-monitor
PROD=/home/amd/helios-rbac
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[1;33m"; NC="\033[0m"

echo -e "${YELLOW}=== Helios DEV → PROD Promotion ===${NC}"
echo "DEV:  http://10.194.168.138:3100"
echo "PROD: http://10.194.168.138:3200"
echo ""

# Pre-promotion checks
echo -e "${YELLOW}[1/5] Health checks...${NC}"
DEV_HEALTH=$(curl -s --max-time 5 http://localhost:8100/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
if [ "$DEV_HEALTH" != "ok" ]; then
  echo -e "${RED}  FAIL: DEV backend not healthy (${DEV_HEALTH})${NC}"; exit 1
fi
echo -e "${GREEN}  DEV backend: OK${NC}"
DEV_FE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3100/ 2>/dev/null)
if [ "$DEV_FE" != "200" ]; then
  echo -e "${RED}  FAIL: DEV frontend HTTP $DEV_FE${NC}"; exit 1
fi
echo -e "${GREEN}  DEV frontend: OK${NC}"

# Check diffs
echo -e "${YELLOW}\n[2/5] Checking changes...${NC}"
DIFFS=$(diff -rq --exclude="*.pyc" --exclude="__pycache__" --exclude=".next" --exclude="node_modules" $DEV/frontend/src $PROD/frontend/src 2>/dev/null | wc -l)
DIFFS_BE=$(diff -rq --exclude="*.pyc" --exclude="__pycache__" $DEV/backend/app $PROD/backend/app 2>/dev/null | grep -v "core\|auth\|admin\|reserv\|superadmin\|export" | wc -l)
echo "  Frontend: $DIFFS files changed"
echo "  Backend:  $DIFFS_BE files changed"
if [ "$DIFFS" = "0" ] && [ "$DIFFS_BE" = "0" ] && [ "$FORCE" != "--force" ]; then
  echo -e "${YELLOW}  No changes. Use --force to promote anyway.${NC}"; exit 0
fi

# Confirm
if [ "$FORCE" != "--force" ]; then
  echo ""; read -p "Promote to PROD? (yes/no): " CONFIRM
  if [ "$CONFIRM" != "yes" ]; then echo "Cancelled."; exit 0; fi
fi

# Sync
echo -e "${YELLOW}\n[3/5] Syncing DEV → PROD source...${NC}"
rsync -av --delete $DEV/frontend/src/ $PROD/frontend/src/ 2>&1 | tail -2
rsync -av --delete $DEV/backend/app/  $PROD/backend/app/  2>&1 | tail -2
echo -e "${GREEN}  Sync complete${NC}"

# Build PROD
echo -e "${YELLOW}\n[4/5] Building PROD frontend...${NC}"
rm -rf $PROD/frontend/.next/cache $PROD/frontend/.next/static 2>/dev/null || true
docker run --rm -v $PROD/frontend:/app \
  -e NEXT_PUBLIC_API_URL=http://10.194.168.138:8200 \
  -w /app node:20-alpine \
  sh -c "npm run build > /tmp/prod_build.log 2>&1 && echo OK > /tmp/prod_bs.txt || echo FAIL > /tmp/prod_bs.txt"
BUILD=$(cat /tmp/prod_bs.txt 2>/dev/null)
if [ "$BUILD" != "OK" ]; then
  echo -e "${RED}  FAIL: Build failed. Check /tmp/prod_build.log${NC}"; exit 1
fi
echo -e "${GREEN}  Build: OK${NC}"
cd $PROD/frontend && docker build --no-cache -f Dockerfile.prebuilt -t fleetmon-rbac-frontend-rbac:latest . 2>&1 | tail -2
cd $PROD && docker compose -p fleetmon-rbac -f docker-compose.rbac.yml --env-file .env.rbac \
  up -d --build backend-rbac frontend-rbac 2>&1 | tail -5

# Verify
echo -e "${YELLOW}\n[5/5] Verifying...${NC}"
sleep 8
PROD_BE=$(curl -s --max-time 8 http://localhost:8200/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
PROD_FE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3200/ 2>/dev/null)
echo -e "${GREEN}  PROD backend: $PROD_BE${NC}"
echo -e "${GREEN}  PROD frontend: HTTP $PROD_FE${NC}"
echo ""
echo -e "${GREEN}=== Promotion complete! $(date) ===${NC}"
echo "  PROD: http://10.194.168.138:3200"
