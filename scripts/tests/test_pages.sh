#!/bin/bash

# Script de teste para demonstrar consulta de páginas de PDF

set -e

API_URL="http://localhost:8080"
TEST_FILE="$1"

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "================================================"
echo "  📄 Teste de Conversão de PDF com Páginas"
echo "================================================"
echo ""

# Verificar se arquivo foi passado
if [ -z "$TEST_FILE" ]; then
    echo -e "${RED}❌ Uso: $0 <caminho_do_pdf>${NC}"
    echo ""
    echo "Exemplo:"
    echo "  $0 /path/to/documento.pdf"
    echo ""
    exit 1
fi

# Verificar se arquivo existe
if [ ! -f "$TEST_FILE" ]; then
    echo -e "${RED}❌ Arquivo não encontrado: $TEST_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}📁 Arquivo: $TEST_FILE${NC}"
echo ""

# 1. Upload do arquivo
echo -e "${YELLOW}[1/6] 📤 Fazendo upload do arquivo...${NC}"
RESPONSE=$(curl -s -X POST "$API_URL/upload" -F "file=@$TEST_FILE")

# Extrair job_id
MAIN_JOB_ID=$(echo "$RESPONSE" | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)

if [ -z "$MAIN_JOB_ID" ]; then
    echo -e "${RED}❌ Erro ao fazer upload${NC}"
    echo "$RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Job criado: $MAIN_JOB_ID${NC}"
echo ""

# 2. Monitorar progresso
echo -e "${YELLOW}[2/6] ⏳ Monitorando progresso...${NC}"
echo ""

while true; do
    STATUS_RESPONSE=$(curl -s "$API_URL/jobs/$MAIN_JOB_ID")

    STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
    PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress":[0-9]*' | cut -d':' -f2)
    TOTAL_PAGES=$(echo "$STATUS_RESPONSE" | grep -o '"total_pages":[0-9]*' | cut -d':' -f2)
    PAGES_COMPLETED=$(echo "$STATUS_RESPONSE" | grep -o '"pages_completed":[0-9]*' | cut -d':' -f2)

    # Limpar linha anterior
    echo -ne "\r"

    if [ ! -z "$TOTAL_PAGES" ] && [ "$TOTAL_PAGES" != "null" ]; then
        echo -ne "   Status: $STATUS | Progress: $PROGRESS% | Páginas: $PAGES_COMPLETED/$TOTAL_PAGES"
    else
        echo -ne "   Status: $STATUS | Progress: $PROGRESS%"
    fi

    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        echo ""
        break
    fi

    sleep 1
done

echo ""

if [ "$STATUS" = "failed" ]; then
    echo -e "${RED}❌ Conversão falhou!${NC}"
    echo "$STATUS_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Conversão completa!${NC}"
echo ""

# 3. Verificar se tem páginas (PDF multi-página)
if [ -z "$TOTAL_PAGES" ] || [ "$TOTAL_PAGES" = "null" ] || [ "$TOTAL_PAGES" -eq 0 ]; then
    echo -e "${BLUE}ℹ️  Documento processado como arquivo único (não é PDF multi-página)${NC}"
    echo ""

    # Pegar resultado direto
    echo -e "${YELLOW}[3/6] 📄 Recuperando resultado...${NC}"
    RESULT=$(curl -s "$API_URL/jobs/$MAIN_JOB_ID/result")
    MARKDOWN=$(echo "$RESULT" | grep -o '"markdown":"[^"]*' | cut -d'"' -f4)

    echo -e "${GREEN}✅ Markdown recuperado (${#MARKDOWN} caracteres)${NC}"
    echo ""
    echo "Primeiros 500 caracteres:"
    echo "---"
    echo "$MARKDOWN" | head -c 500
    echo ""
    echo "---"

else
    echo -e "${BLUE}📑 PDF com $TOTAL_PAGES páginas detectado${NC}"
    echo ""

    # 3. Listar páginas
    echo -e "${YELLOW}[3/6] 📋 Listando páginas...${NC}"
    PAGES_RESPONSE=$(curl -s "$API_URL/jobs/$MAIN_JOB_ID/pages")

    echo "$PAGES_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"Total de páginas: {data['total_pages']}\")
    print(f\"Páginas completadas: {data['pages_completed']}\")
    print(f\"Páginas com erro: {data['pages_failed']}\")
    print()
    print('Páginas:')
    for page in data['pages'][:5]:  # Mostrar primeiras 5
        print(f\"  - Página {page['page_number']}: {page['status']} (Job ID: {page['job_id']})\")
    if len(data['pages']) > 5:
        print(f\"  ... e mais {len(data['pages']) - 5} páginas\")
except:
    print(sys.stdin.read())
"

    echo ""

    # 4. Pegar resultado da primeira página
    echo -e "${YELLOW}[4/6] 📖 Recuperando página 1...${NC}"

    PAGE_1_ID=$(echo "$PAGES_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for page in data['pages']:
        if page['page_number'] == 1:
            print(page['job_id'])
            break
except:
    pass
")

    if [ ! -z "$PAGE_1_ID" ]; then
        PAGE_1_RESULT=$(curl -s "$API_URL/jobs/$PAGE_1_ID/result")
        PAGE_1_MARKDOWN=$(echo "$PAGE_1_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['result']['markdown'])
except:
    pass
")

        echo -e "${GREEN}✅ Página 1 recuperada (${#PAGE_1_MARKDOWN} caracteres)${NC}"
        echo ""
        echo "Primeiros 300 caracteres da página 1:"
        echo "---"
        echo "$PAGE_1_MARKDOWN" | head -c 300
        echo ""
        echo "---"
        echo ""
    else
        echo -e "${RED}❌ Não foi possível recuperar página 1${NC}"
        echo ""
    fi

    # 5. Pegar resultado completo (merged)
    echo -e "${YELLOW}[5/6] 📚 Recuperando documento completo (merged)...${NC}"
    FULL_RESULT=$(curl -s "$API_URL/jobs/$MAIN_JOB_ID/result")
    FULL_MARKDOWN=$(echo "$FULL_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['result']['markdown'])
except:
    pass
")

    echo -e "${GREEN}✅ Documento completo recuperado (${#FULL_MARKDOWN} caracteres)${NC}"
    echo ""
    echo "Primeiros 500 caracteres do documento completo:"
    echo "---"
    echo "$FULL_MARKDOWN" | head -c 500
    echo ""
    echo "---"
    echo ""
fi

# 6. Resumo
echo -e "${YELLOW}[6/6] 📊 Resumo:${NC}"
echo ""
echo "  Main Job ID: $MAIN_JOB_ID"
echo "  Status: $STATUS"
echo "  Total de páginas: ${TOTAL_PAGES:-N/A}"
echo ""
echo "  Endpoints disponíveis:"
echo "    - Status: $API_URL/jobs/$MAIN_JOB_ID"
echo "    - Resultado: $API_URL/jobs/$MAIN_JOB_ID/result"

if [ ! -z "$TOTAL_PAGES" ] && [ "$TOTAL_PAGES" != "null" ] && [ "$TOTAL_PAGES" -gt 0 ]; then
    echo "    - Páginas: $API_URL/jobs/$MAIN_JOB_ID/pages"

    if [ ! -z "$PAGE_1_ID" ]; then
        echo "    - Página 1: $API_URL/jobs/$PAGE_1_ID/result"
    fi
fi

echo ""
echo -e "${GREEN}✅ Teste concluído com sucesso!${NC}"
echo ""
