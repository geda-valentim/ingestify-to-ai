#!/bin/bash

# Test script for pagination on GET /jobs/{job_id}

API_URL="http://localhost:8000"
JOB_ID="7fbdfd62-013b-47fd-8d9c-4300402c9a95"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Testing Job Pagination ===${NC}\n"

# Test 1: Get ALL pages (no pagination)
echo -e "${GREEN}Test 1: Get ALL pages (no pagination)${NC}"
curl -s "$API_URL/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"Total pages: {data.get('total_pages', 'N/A')}\")
print(f\"Pages returned: {len(data.get('pages', []))}\")
if data.get('pages'):
    pages = data['pages']
    print(f\"First page: {pages[0]['page_number']}\")
    print(f\"Last page: {pages[-1]['page_number']}\")
"
echo -e "\n"

# Test 2: Get first 50 pages
echo -e "${GREEN}Test 2: Get first 50 pages (page_limit=50, page_offset=0)${NC}"
curl -s "$API_URL/jobs/$JOB_ID?page_limit=50&page_offset=0" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"Total pages: {data.get('total_pages', 'N/A')}\")
print(f\"Pages returned: {len(data.get('pages', []))}\")
if data.get('pages'):
    pages = data['pages']
    print(f\"First page: {pages[0]['page_number']}\")
    print(f\"Last page: {pages[-1]['page_number']}\")
print(f\"Pages completed: {data.get('pages_completed', 'N/A')}\")
print(f\"Pages failed: {data.get('pages_failed', 'N/A')}\")
"
echo -e "\n"

# Test 3: Get next 50 pages (offset 50)
echo -e "${GREEN}Test 3: Get pages 51-100 (page_limit=50, page_offset=50)${NC}"
curl -s "$API_URL/jobs/$JOB_ID?page_limit=50&page_offset=50" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"Total pages: {data.get('total_pages', 'N/A')}\")
print(f\"Pages returned: {len(data.get('pages', []))}\")
if data.get('pages'):
    pages = data['pages']
    print(f\"First page: {pages[0]['page_number']}\")
    print(f\"Last page: {pages[-1]['page_number']}\")
"
echo -e "\n"

# Test 4: Get pages 200-229 (last pages)
echo -e "${GREEN}Test 4: Get last pages (page_limit=30, page_offset=199)${NC}"
curl -s "$API_URL/jobs/$JOB_ID?page_limit=30&page_offset=199" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"Total pages: {data.get('total_pages', 'N/A')}\")
print(f\"Pages returned: {len(data.get('pages', []))}\")
if data.get('pages'):
    pages = data['pages']
    print(f\"First page: {pages[0]['page_number']}\")
    print(f\"Last page: {pages[-1]['page_number']}\")
"
echo -e "\n"

echo -e "${BLUE}=== Pagination Tests Complete ===${NC}"
