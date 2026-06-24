#!/bin/bash
# dev-deploy.sh — Build and restart DEV (3100) stack
# Usage: ./dev-deploy.sh [--frontend-only | --backend-only | --all]
set -e
DEV=/home/amd/fleet-monitor
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"
MODE=${1:-"--all"}

echo -e "${YELLOW}=== DEV Stack Rebuild ($MODE) ===${NC}"

if [ "$MODE" = "--backend-only" ]; then
  echo "Rebuilding DEV backend..."
  cd $DEV && docker compose -p fleetmon-ai -f docker-compose.ai.yml up -d --build --no-deps backend 2>&1 | tail -4
  sleep 5
  STATUS=$(curl -s http://localhost:8100/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo -e "${GREEN}DEV backend: $STATUS${NC}"

elif [ "$MODE" = "--frontend-only" ]; then
  echo "Building DEV frontend..."
  rm -rf $DEV/frontend/.next/cache $DEV/frontend/.next/static 2>/dev/null || true
  docker run --rm -v $DEV/frontend:/app \
    -e NEXT_PUBLIC_API_URL=http://10.194.168.138:8100 \
    -w /app node:20-alpine \
    sh -c "npm run build > /tmp/dev_build.log 2>&1 && echo OK > /tmp/dev_bs.txt || echo FAIL > /tmp/dev_bs.txt"
  echo "  Build: $(cat /tmp/dev_bs.txt)"
  cd $DEV/frontend && docker build --no-cache -f Dockerfile.prebuilt -t fleetmon-ai-frontend:latest . 2>&1 | tail -2
  cd $DEV && docker compose -p fleetmon-ai -f docker-compose.ai.yml up -d --no-build frontend 2>&1 | tail -3
  echo -e "${GREEN}DEV frontend: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/)${NC}"

else
  echo "Full DEV rebuild..."
  cd $DEV && docker compose -p fleetmon-ai -f docker-compose.ai.yml up -d --build 2>&1 | tail -6
  sleep 5
  STATUS=$(curl -s http://localhost:8100/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo -e "${GREEN}DEV backend:  $STATUS${NC}"
  echo -e "${GREEN}DEV frontend: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/)${NC}"
fi

echo ""
echo "DEV: http://10.194.168.138:3100  $(date)"
