#!/bin/bash
# Test script for /upload endpoint using API Key authentication

set -e

API_URL="http://localhost:8000"
UPLOAD_ENDPOINT="$API_URL/upload"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Upload Endpoint with API Key Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if API key is provided as argument
if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: $0 <api-key> [file-path]${NC}"
    echo ""
    echo "Example:"
    echo "  $0 doc2md_sk_abc123 /path/to/file.pdf"
    echo ""
    echo -e "${YELLOW}To create an API key:${NC}"
    echo "1. First login to get JWT token:"
    echo "   curl -X POST $API_URL/auth/login \\"
    echo "     -H 'Content-Type: application/json' \\"
    echo "     -d '{\"username\":\"your_username\",\"password\":\"your_password\"}'"
    echo ""
    echo "2. Then create API key using the token:"
    echo "   curl -X POST $API_URL/api-keys/ \\"
    echo "     -H 'Authorization: Bearer YOUR_JWT_TOKEN' \\"
    echo "     -H 'Content-Type: application/json' \\"
    echo "     -d '{\"name\":\"My API Key\",\"expires_in_days\":30}'"
    echo ""
    exit 1
fi

API_KEY="$1"
FILE_PATH="${2:-/home/geda/curso-327569-aula-04-a0b8-completo.pdf}"

# Check if file exists
if [ ! -f "$FILE_PATH" ]; then
    echo -e "${RED}Error: File not found: $FILE_PATH${NC}"
    exit 1
fi

echo -e "${BLUE}Configuration:${NC}"
echo "  API URL: $API_URL"
echo "  API Key: ${API_KEY:0:20}..."
echo "  File: $FILE_PATH"
echo ""

# Test 1: Upload with fast preset (default)
echo -e "${YELLOW}Test 1: Upload with fast preset (text-only, ~35s/MB)${NC}"
echo ""

RESPONSE=$(curl -s -X POST "$UPLOAD_ENDPOINT" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@$FILE_PATH" \
  -F "name=Test Upload via API Key (Fast)" \
  -F "docling_preset=fast")

echo "Response:"
echo "$RESPONSE" | jq .

if echo "$RESPONSE" | jq -e '.job_id' > /dev/null 2>&1; then
    JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')
    echo -e "${GREEN}✓ Upload successful!${NC}"
    echo -e "${GREEN}Job ID: $JOB_ID${NC}"
    echo ""
    echo -e "${BLUE}Track job status:${NC}"
    echo "  curl -H \"X-API-Key: $API_KEY\" $API_URL/jobs/$JOB_ID"
    echo ""
    echo -e "${BLUE}Get result (when completed):${NC}"
    echo "  curl -H \"X-API-Key: $API_KEY\" $API_URL/jobs/$JOB_ID/result"
    echo ""
else
    echo -e "${RED}✗ Upload failed${NC}"
    exit 1
fi

# Test 2: Upload with quality preset (with OCR)
echo ""
echo -e "${YELLOW}Test 2: Upload with quality preset (with OCR, ~350s/MB)${NC}"
echo ""

RESPONSE2=$(curl -s -X POST "$UPLOAD_ENDPOINT" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@$FILE_PATH" \
  -F "name=Test Upload via API Key (Quality)" \
  -F "docling_preset=quality")

echo "Response:"
echo "$RESPONSE2" | jq .

if echo "$RESPONSE2" | jq -e '.job_id' > /dev/null 2>&1; then
    JOB_ID2=$(echo "$RESPONSE2" | jq -r '.job_id')
    echo -e "${GREEN}✓ Upload successful!${NC}"
    echo -e "${GREEN}Job ID: $JOB_ID2${NC}"
else
    echo -e "${RED}✗ Upload failed${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}All tests completed!${NC}"
echo -e "${BLUE}========================================${NC}"
