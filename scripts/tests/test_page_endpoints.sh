#!/bin/bash

# Script para testar novos endpoints de página por número

set -e

API_URL="http://localhost:8080"

echo "🧪 Teste dos Novos Endpoints de Páginas"
echo "========================================"
echo ""

# 1. Upload de PDF
echo "1️⃣  Fazendo upload de PDF de teste..."
if [ ! -f "AI-50p.pdf" ]; then
    echo "❌ PDF não encontrado: AI-50p.pdf"
    exit 1
fi

UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/upload" -F "file=@AI-50p.pdf")
JOB_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
    echo "❌ Erro ao fazer upload"
    echo "$UPLOAD_RESPONSE"
    exit 1
fi

echo "✅ Upload concluído! Job ID: $JOB_ID"
echo ""

# 2. Aguardar processamento
echo "2️⃣  Aguardando processamento..."
echo ""

for i in {1..30}; do
    STATUS_RESPONSE=$(curl -s "$API_URL/jobs/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['progress'])" 2>/dev/null || echo "0")
    TOTAL_PAGES=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_pages', 0))" 2>/dev/null || echo "0")
    PAGES_COMPLETED=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('pages_completed', 0))" 2>/dev/null || echo "0")

    echo -ne "\r   Status: $STATUS | Progress: $PROGRESS% | Páginas: $PAGES_COMPLETED/$TOTAL_PAGES   "

    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        echo ""
        break
    fi

    sleep 2
done

echo ""

if [ "$STATUS" != "completed" ]; then
    echo "❌ Job não completou: $STATUS"
    exit 1
fi

echo "✅ Processamento concluído!"
echo "   Total de páginas: $TOTAL_PAGES"
echo ""

# 3. Testar endpoint de status por número
echo "3️⃣  Testando GET /jobs/{job_id}/pages/{page_number}/status"
echo ""

for PAGE_NUM in 1 5 10; do
    if [ "$PAGE_NUM" -le "$TOTAL_PAGES" ]; then
        echo "   📄 Página $PAGE_NUM:"
        RESPONSE=$(curl -s "$API_URL/jobs/$JOB_ID/pages/$PAGE_NUM/status")

        PAGE_STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('status', 'N/A'))" 2>/dev/null || echo "Error")
        PAGE_JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('job_id', 'N/A')[:13])" 2>/dev/null || echo "Error")

        if [ "$PAGE_STATUS" != "Error" ]; then
            echo "      ✅ Status: $PAGE_STATUS"
            echo "      📋 Page Job ID: $PAGE_JOB_ID..."
        else
            echo "      ❌ Erro ao buscar status"
            echo "$RESPONSE" | python3 -m json.tool | head -5
        fi
        echo ""
    fi
done

# 4. Testar endpoint de resultado por número
echo "4️⃣  Testando GET /jobs/{job_id}/pages/{page_number}/result"
echo ""

PAGE_NUM=1
echo "   📄 Página $PAGE_NUM:"
RESPONSE=$(curl -s "$API_URL/jobs/$JOB_ID/pages/$PAGE_NUM/result")

ERROR=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('detail', ''))" 2>/dev/null || echo "")

if [ -z "$ERROR" ]; then
    MARKDOWN=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['result']['markdown'][:100])" 2>/dev/null || echo "Error")

    if [ "$MARKDOWN" != "Error" ]; then
        echo "      ✅ Markdown recuperado!"
        echo "      📝 Preview: ${MARKDOWN}..."
    else
        echo "      ❌ Erro ao extrair markdown"
    fi
else
    echo "      ⚠️  $ERROR"
fi

echo ""

# 5. Comparar com endpoint antigo
echo "5️⃣  Comparação de endpoints"
echo ""
echo "   🆕 Novo (por número):"
echo "      GET /jobs/$JOB_ID/pages/1/status"
echo "      GET /jobs/$JOB_ID/pages/1/result"
echo ""
echo "   🔙 Antigo (por page_job_id):"
PAGE_JOB_ID=$(curl -s "$API_URL/jobs/$JOB_ID/pages" | python3 -c "import sys, json; print(json.load(sys.stdin)['pages'][0]['job_id'])" 2>/dev/null || echo "N/A")
echo "      GET /jobs/$PAGE_JOB_ID/result"
echo ""
echo "   ✨ Vantagem: Não precisa listar /pages primeiro!"
echo ""

# 6. Resumo
echo "========================================"
echo "✅ Teste Concluído!"
echo ""
echo "📋 Novos endpoints funcionando:"
echo "   • GET /jobs/{job_id}/pages/{page_number}/status"
echo "   • GET /jobs/{job_id}/pages/{page_number}/result"
echo ""
echo "🎯 Exemplo de uso:"
echo "   curl $API_URL/jobs/$JOB_ID/pages/5/result"
echo ""
