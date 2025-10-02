#!/bin/bash
# Script para limpar Docker e recomeçar do zero

set -e

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                        Limpeza Completa do Docker                           ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

echo "⚠️  ATENÇÃO: Este script vai remover:"
echo "   • Containers do doc2md"
echo "   • Imagens do doc2md"
echo "   • Volumes do doc2md"
echo "   • Cache de build (opcional)"
echo ""

read -p "Tem certeza? [s/N]: " confirm

if [ "$confirm" != "s" ]; then
    echo "Operação cancelada."
    exit 0
fi

echo ""
echo "🛑 Parando containers..."
docker compose down -v 2>/dev/null || true
echo "✓ Containers parados"

echo ""
echo "🗑️  Removendo containers..."
docker ps -a | grep doc2md | awk '{print $1}' | xargs -r docker rm -f 2>/dev/null || true
echo "✓ Containers removidos"

echo ""
echo "🗑️  Removendo imagens..."
docker images | grep doc2md | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
echo "✓ Imagens removidas"

echo ""
echo "🗑️  Removendo volumes..."
docker volume ls | grep doc2md | awk '{print $2}' | xargs -r docker volume rm 2>/dev/null || true
echo "✓ Volumes removidos"

echo ""
read -p "Deseja limpar o cache de build do Docker também? [s/N]: " clean_cache

if [ "$clean_cache" = "s" ]; then
    echo ""
    echo "🧹 Limpando cache de build..."
    docker builder prune -af
    echo "✓ Cache limpo"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                         ✅ LIMPEZA CONCLUÍDA!                                ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Mostrar espaço recuperado
echo "💾 Espaço em disco do Docker:"
docker system df
echo ""

echo "🚀 Para rebuildar:"
echo "   ./scripts/docker-build.sh"
echo ""
