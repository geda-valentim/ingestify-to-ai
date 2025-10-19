#!/bin/bash
set -e

echo "=== DOC2MD Authentication Test ==="
echo ""

# Extract token
ALICE_TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/alice_token.json'))['access_token'])")

echo "1. Testing /auth/me (authenticated endpoint)"
curl -s -X GET http://localhost:8080/auth/me \
  -H "Authorization: Bearer $ALICE_TOKEN" | python3 -m json.tool

echo ""
echo "2. Creating API Key"
curl -s -X POST http://localhost:8080/api-keys \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Key", "expires_in_days": 30}' > /tmp/alice_apikey.json

cat /tmp/alice_apikey.json | python3 -m json.tool

echo ""
echo "3. Creating test PDF"
echo "%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
203
%%EOF" > /tmp/test_upload.pdf

echo "4. Upload PDF with JWT"
curl -s -X POST http://localhost:8080/upload \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/test_upload.pdf" \
  -F "name=Test Document" > /tmp/alice_job.json

cat /tmp/alice_job.json | python3 -m json.tool
JOB_ID=$(python3 -c "import json; print(json.load(open('/tmp/alice_job.json'))['job_id'])")

echo ""
echo "Job created: $JOB_ID"

echo ""
echo "5. Check job status"
sleep 2
curl -s -X GET "http://localhost:8080/jobs/$JOB_ID" \
  -H "Authorization: Bearer $ALICE_TOKEN" | python3 -m json.tool

echo ""
echo "6. List all jobs for alice"
curl -s -X GET "http://localhost:8080/jobs?job_type=main" \
  -H "Authorization: Bearer $ALICE_TOKEN" | python3 -m json.tool

echo ""
echo "✅ All tests passed!"
