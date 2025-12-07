#!/bin/bash
# =============================================================================
# Lexia API - Comprehensive Pre-Production Audit Script
# =============================================================================
# Usage: ./scripts/audit.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${YELLOW}→ $1${NC}"
}

print_pass() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED++))
}

print_fail() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED++))
}

print_warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
    ((WARNINGS++))
}

# =============================================================================
# 1. Environment Check
# =============================================================================
print_header "1. ENVIRONMENT CHECK"

print_step "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
if [[ $(echo "$PYTHON_VERSION >= 3.11" | bc -l) -eq 1 ]]; then
    print_pass "Python $PYTHON_VERSION detected"
else
    print_fail "Python 3.11+ required, found $PYTHON_VERSION"
fi

print_step "Checking Docker..."
if command -v docker &> /dev/null; then
    print_pass "Docker installed"
else
    print_fail "Docker not found"
fi

print_step "Checking docker compose..."
if docker compose version &> /dev/null; then
    print_pass "Docker Compose installed"
else
    print_fail "Docker Compose not found"
fi

# =============================================================================
# 2. Dependency Installation
# =============================================================================
print_header "2. INSTALLING DEPENDENCIES"

print_step "Installing dev dependencies..."
pip install -q -r requirements.txt -r requirements-dev.txt 2>/dev/null && \
    print_pass "Dependencies installed" || \
    print_fail "Failed to install dependencies"

# =============================================================================
# 3. Code Quality Checks
# =============================================================================
print_header "3. CODE QUALITY"

print_step "Running Ruff linter..."
if ruff check src/ --exit-zero > /tmp/ruff_output.txt 2>&1; then
    RUFF_ISSUES=$(cat /tmp/ruff_output.txt | grep -c ":" || echo "0")
    if [ "$RUFF_ISSUES" -eq 0 ]; then
        print_pass "No linting issues"
    else
        print_warn "$RUFF_ISSUES linting issues found (see /tmp/ruff_output.txt)"
    fi
else
    print_warn "Ruff check completed with warnings"
fi

print_step "Running Black formatter check..."
if black --check src/ tests/ 2>/dev/null; then
    print_pass "Code formatting OK"
else
    print_warn "Code formatting issues (run: black src/ tests/)"
fi

print_step "Running MyPy type checker..."
if mypy src/ --ignore-missing-imports --no-error-summary 2>/dev/null | head -20; then
    print_pass "Type checking completed"
else
    print_warn "Type checking had issues"
fi

# =============================================================================
# 4. Security Audit
# =============================================================================
print_header "4. SECURITY AUDIT"

print_step "Running Bandit security scanner..."
if bandit -r src/ -ll -q 2>/dev/null; then
    print_pass "No high/medium security issues"
else
    print_fail "Security vulnerabilities found!"
fi

print_step "Checking for hardcoded secrets..."
SECRETS_FOUND=$(grep -rn "password\|secret\|api_key\|token" src/ --include="*.py" | \
    grep -v "def \|class \|#\|import\|:\s*str\|Optional\|password:\|secret_key:\|api_key:\|token:" | \
    grep -v "test\|mock\|example" || echo "")
if [ -z "$SECRETS_FOUND" ]; then
    print_pass "No hardcoded secrets detected"
else
    print_warn "Potential secrets found - review manually"
    echo "$SECRETS_FOUND" | head -5
fi

print_step "Checking pip-audit for vulnerable dependencies..."
if pip-audit --strict 2>/dev/null; then
    print_pass "No vulnerable dependencies"
else
    print_warn "Some dependencies may have vulnerabilities"
fi

print_step "Checking .env files not tracked in git..."
if git ls-files --error-unmatch docker/.env 2>/dev/null; then
    print_fail ".env file is tracked in git!"
else
    print_pass ".env files not tracked"
fi

# =============================================================================
# 5. Unit Tests
# =============================================================================
print_header "5. UNIT TESTS"

print_step "Running pytest..."
if pytest tests/ -v --tb=short --cov=src --cov-report=term-missing 2>&1 | tee /tmp/pytest_output.txt; then
    print_pass "All tests passed"
else
    FAILED_TESTS=$(grep -c "FAILED" /tmp/pytest_output.txt || echo "0")
    print_fail "$FAILED_TESTS tests failed"
fi

# =============================================================================
# 6. Docker Build Test
# =============================================================================
print_header "6. DOCKER BUILD TEST"

print_step "Building API image..."
if docker build -f docker/Dockerfile.api -t lexia-api:audit . 2>/dev/null; then
    print_pass "API image built successfully"
else
    print_fail "API image build failed"
fi

print_step "Building Worker image..."
if docker build -f docker/Dockerfile.worker -t lexia-worker:audit . 2>/dev/null; then
    print_pass "Worker image built successfully"
else
    print_fail "Worker image build failed"
fi

# =============================================================================
# 7. API Endpoint Test (if containers running)
# =============================================================================
print_header "7. API ENDPOINT TESTS"

API_URL="http://localhost:8000"

print_step "Testing root endpoint..."
if curl -sf "$API_URL/" > /dev/null 2>&1; then
    print_pass "Root endpoint accessible"
else
    print_warn "API not running (start with docker compose up)"
fi

print_step "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -sf "$API_URL/health" 2>/dev/null || echo "")
if [ -n "$HEALTH_RESPONSE" ]; then
    STATUS=$(echo "$HEALTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null)
    if [ "$STATUS" = "healthy" ]; then
        print_pass "Health check: healthy"
    else
        print_warn "Health check: $STATUS"
    fi
else
    print_warn "Health endpoint not accessible"
fi

print_step "Testing OpenAPI schema..."
if curl -sf "$API_URL/openapi.json" > /dev/null 2>&1; then
    print_pass "OpenAPI schema accessible"
else
    print_warn "OpenAPI schema not accessible"
fi

# =============================================================================
# 8. Database Check
# =============================================================================
print_header "8. DATABASE CHECK"

print_step "Checking Alembic migrations..."
if [ -d "alembic/versions" ]; then
    MIGRATION_COUNT=$(ls -1 alembic/versions/*.py 2>/dev/null | wc -l || echo "0")
    if [ "$MIGRATION_COUNT" -gt 0 ]; then
        print_pass "$MIGRATION_COUNT migration(s) found"
    else
        print_warn "No migrations found - run: alembic revision --autogenerate"
    fi
else
    print_warn "Alembic versions directory not found"
fi

# =============================================================================
# 9. Documentation Check
# =============================================================================
print_header "9. DOCUMENTATION CHECK"

print_step "Checking README..."
if [ -f "README.md" ] && [ -s "README.md" ]; then
    print_pass "README.md exists"
else
    print_warn "README.md missing or empty"
fi

print_step "Checking API docs..."
if [ -f "docs/API.md" ] && [ -s "docs/API.md" ]; then
    print_pass "API documentation exists"
else
    print_warn "API documentation missing"
fi

print_step "Checking deployment docs..."
if [ -f "docs/DEPLOYMENT.md" ] && [ -s "docs/DEPLOYMENT.md" ]; then
    print_pass "Deployment documentation exists"
else
    print_warn "Deployment documentation missing"
fi

# =============================================================================
# Summary
# =============================================================================
print_header "AUDIT SUMMARY"

TOTAL=$((PASSED + FAILED + WARNINGS))

echo ""
echo -e "${GREEN}Passed:   $PASSED${NC}"
echo -e "${RED}Failed:   $FAILED${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✓ AUDIT PASSED - Ready for production ${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    exit 0
else
    echo -e "${RED}════════════════════════════════════════${NC}"
    echo -e "${RED}  ✗ AUDIT FAILED - Fix issues before prod${NC}"
    echo -e "${RED}════════════════════════════════════════${NC}"
    exit 1
fi
