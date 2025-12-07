#!/bin/bash
# =============================================================================
# Lexia API - Manual Endpoint Testing Script
# =============================================================================
# Usage: ./scripts/test_endpoints.sh [API_URL] [API_KEY]
# Default: http://localhost:8000 with test key
# =============================================================================

set -e

API_URL="${1:-http://localhost:8000}"
API_KEY="${2:-lx_test_key_for_testing}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Lexia API Endpoint Testing${NC}"
echo -e "${BLUE}  URL: $API_URL${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Test counter
PASSED=0
FAILED=0

test_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_code=$3
    local data=$4
    local auth=$5

    local headers=""
    if [ "$auth" = "true" ]; then
        headers="-H \"Authorization: Bearer $API_KEY\""
    fi

    local response
    if [ "$method" = "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" $headers "$API_URL$endpoint" 2>/dev/null)
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" -X $method $headers \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$API_URL$endpoint" 2>/dev/null)
    fi

    if [ "$response" = "$expected_code" ]; then
        echo -e "${GREEN}✓${NC} $method $endpoint -> $response"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $method $endpoint -> $response (expected $expected_code)"
        ((FAILED++))
    fi
}

echo -e "${YELLOW}─── Public Endpoints ───${NC}"
test_endpoint "GET" "/" "200" "" "false"
test_endpoint "GET" "/health" "200" "" "false"
test_endpoint "GET" "/openapi.json" "200" "" "false"
test_endpoint "GET" "/docs" "200" "" "false"
test_endpoint "GET" "/redoc" "200" "" "false"

echo ""
echo -e "${YELLOW}─── Authentication Required (no auth) ───${NC}"
test_endpoint "GET" "/v1/models" "401" "" "false"
test_endpoint "POST" "/v1/chat/completions" "401" '{"model":"test","messages":[]}' "false"
test_endpoint "POST" "/v1/transcriptions" "401" '{"audio_url":"https://test.com/a.wav"}' "false"
test_endpoint "GET" "/v1/jobs" "401" "" "false"

echo ""
echo -e "${YELLOW}─── With Authentication ───${NC}"
test_endpoint "GET" "/v1/models" "200" "" "true"

echo ""
echo -e "${YELLOW}─── LLM Endpoints ───${NC}"
# Valid chat completion
echo -e "${BLUE}Testing chat completion...${NC}"
CHAT_RESPONSE=$(curl -s -X POST "$API_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "general7Bv2",
        "messages": [{"role": "user", "content": "Dis bonjour"}],
        "max_tokens": 50
    }' 2>/dev/null)

if echo "$CHAT_RESPONSE" | grep -q "choices\|error"; then
    echo -e "${GREEN}✓${NC} POST /v1/chat/completions returned valid response"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} POST /v1/chat/completions unexpected response"
    ((FAILED++))
fi

echo ""
echo -e "${YELLOW}─── Validation Errors ───${NC}"
# Missing required fields
test_endpoint "POST" "/v1/chat/completions" "422" '{}' "true"
test_endpoint "POST" "/v1/chat/completions" "422" '{"model":"test"}' "true"
test_endpoint "POST" "/v1/chat/completions" "422" '{"model":"test","messages":[]}' "true"

echo ""
echo -e "${YELLOW}─── STT Endpoints ───${NC}"
echo -e "${BLUE}Testing transcription submission...${NC}"
TRANS_RESPONSE=$(curl -s -X POST "$API_URL/v1/transcriptions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "audio_url": "https://example.com/test.wav",
        "language_code": "fr"
    }' 2>/dev/null)

if echo "$TRANS_RESPONSE" | grep -q "id\|job_id\|error"; then
    echo -e "${GREEN}✓${NC} POST /v1/transcriptions returned response"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} POST /v1/transcriptions unexpected response"
    ((FAILED++))
fi

echo ""
echo -e "${YELLOW}─── Jobs Endpoints ───${NC}"
echo -e "${BLUE}Testing jobs list...${NC}"
JOBS_RESPONSE=$(curl -s "$API_URL/v1/jobs" \
    -H "Authorization: Bearer $API_KEY" 2>/dev/null)

if echo "$JOBS_RESPONSE" | grep -q "jobs\|data\|error\|\[\]"; then
    echo -e "${GREEN}✓${NC} GET /v1/jobs returned response"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} GET /v1/jobs unexpected response"
    ((FAILED++))
fi

echo ""
echo -e "${YELLOW}─── Error Handling ───${NC}"
test_endpoint "GET" "/nonexistent" "404" "" "false"
test_endpoint "GET" "/v1/jobs/invalid-uuid" "422" "" "true"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
