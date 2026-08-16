#!/bin/bash

# E2E Test Runner
# Usage: ./run-e2e-tests.sh [ui|debug]

set -e

MODE="${1:-headless}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "EAIStack E2E Test Runner"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if services are running
echo "[1/4] Checking services..."
for service in keycloak backend; do
  case $service in
    keycloak) url="http://localhost:8080/realms/eaistack" ;;
    backend) url="http://localhost:8001/health" ;;
  esac

  if curl -s "$url" > /dev/null; then
    echo "  ✓ $service is running"
  else
    echo "  ✗ $service is NOT running"
    echo ""
    echo "ERROR: Services not ready. Please run:"
    echo "  docker-compose up"
    exit 1
  fi
done
echo ""

# Check Playwright is installed
echo "[2/4] Checking Playwright..."
cd frontend
if ! npm list @playwright/test > /dev/null 2>&1; then
  echo "  Installing Playwright..."
  npm install -D @playwright/test
fi
echo "  ✓ Playwright ready"
echo ""

# Run tests
echo "[3/4] Running tests..."
case $MODE in
  ui)
    echo "  → Interactive UI mode"
    npm run test:e2e:ui
    ;;
  debug)
    echo "  → Debug mode"
    npm run test:e2e:debug
    ;;
  *)
    echo "  → Headless mode"
    npm run test:e2e
    ;;
esac

echo ""
echo "[4/4] Results"
if [ -f "playwright-report/index.html" ]; then
  echo "  ✓ Report generated: playwright-report/index.html"
  if [ -f "test-results.json" ]; then
    echo "  ✓ JSON results: test-results.json"
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "E2E Tests Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
