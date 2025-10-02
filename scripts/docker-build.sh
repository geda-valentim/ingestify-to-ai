#!/bin/bash
# Script otimizado para build do Docker com cache de pip

set -e

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                      Docker Build com Cache Otimizado                       ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Habilitar BuildKit para usar cache mounts
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "🔧 Docker BuildKit: HABILITADO"
echo "   Isso permite cache de /root/.cache/pip"
echo ""

# Verificar se há build anterior
if docker images | grep -q "doc2md"; then
    echo "📦 Imagens existentes encontradas:"
    docker images | grep doc2md | head -5
    echo ""

    read -p "Deseja fazer build incremental (i) ou limpar cache (c)? [i/c]: " choice

    if [ "$choice" = "c" ]; then
        echo ""
        echo "🧹 Limpando cache de build..."
        docker builder prune -f
        echo "✓ Cache limpo"
        echo ""
    fi
fi

echo "🏗️  Iniciando build..."
echo ""
echo "📥 Etapa 1: Construindo imagem API..."
echo "   Packages serão cacheados em /root/.cache/pip"
echo ""

docker compose build api

echo ""
echo "✓ API build concluído"
echo ""
echo "📥 Etapa 2: Construindo imagem Worker..."
echo "   Reutilizando cache de packages da API"
echo ""

docker compose build worker

echo ""
echo "✓ Worker build concluído"
echo ""

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                           ✅ BUILD CONCLUÍDO!                                ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Mostrar tamanho das imagens
echo "📊 Tamanho das imagens criadas:"
docker images | grep -E "REPOSITORY|doc2md"
echo ""

# Mostrar cache info
echo "💾 Cache de build do Docker:"
docker system df -v | grep -A 5 "Build Cache"
echo ""

echo "🚀 Próximos passos:"
echo ""
echo "   # Modo produção:"
echo "   docker compose up -d"
echo ""
echo "   # Modo desenvolvimento (com hot-reload):"
echo "   docker compose -f docker-compose.yml -f docker-compose.dev.yml up"
echo ""
echo "   # Ver logs:"
echo "   docker compose logs -f"
echo ""
