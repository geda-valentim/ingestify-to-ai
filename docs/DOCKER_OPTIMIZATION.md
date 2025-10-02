# Otimizações de Docker - Doc2MD

## 🚀 Problema Resolvido

O build do Docker estava **muito lento** porque:
- PyTorch tem **~888 MB** de download
- Docling e dependências somam **~1.5 GB** no total
- Cada rebuild baixava tudo novamente (mesmo sem mudanças)
- Tempo total: **10+ minutos** por build

## ✅ Solução Implementada

### 1. Cache de Packages do Pip

Adicionado `--mount=type=cache` nos Dockerfiles:

```dockerfile
# Antes (SEM cache)
RUN pip install --no-cache-dir -r requirements.txt

# Depois (COM cache)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

**Benefícios:**
- ✅ Primeiro build: baixa tudo normalmente (~10 min)
- ✅ Rebuilds: reutiliza cache (~30 segundos)
- ✅ Cache compartilhado entre api e worker
- ✅ Não aumenta tamanho da imagem final

### 2. Docker BuildKit

Os scripts agora habilitam BuildKit automaticamente:

```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

**Recursos habilitados:**
- Cache mounts (`--mount=type=cache`)
- Build paralelo de múltiplos stages
- Output de build mais limpo
- Melhor performance geral

### 3. Docker Compose para Desenvolvimento

Criado `docker-compose.dev.yml` com:
- **Volumes montados**: código atualiza sem rebuild
- **Hot-reload**: uvicorn e celery recarregam automaticamente
- **Pool solo**: Celery usa pool solo para hot-reload funcionar

```bash
# Modo desenvolvimento
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## 📊 Comparação de Performance

### Primeiro Build (cache vazio)
```
Sem otimização:  ~10-12 minutos
Com otimização:  ~10-12 minutos (igual)
```

### Rebuild (mudança no código)
```
Sem otimização:  ~10-12 minutos (baixa tudo de novo)
Com otimização:  ~30-60 segundos (reutiliza cache)
```

### Desenvolvimento (com hot-reload)
```
Sem otimização:  Rebuild necessário a cada mudança
Com otimização:  0 segundos (hot-reload automático)
```

**Economia de tempo:** ~10 minutos por rebuild! 🎉

## 🛠️ Scripts Criados

### 1. docker-build.sh
Build otimizado com cache:

```bash
./scripts/docker-build.sh
```

**Features:**
- Habilita BuildKit automaticamente
- Mostra tamanho das imagens
- Mostra cache disponível
- Opção de build incremental ou limpar cache

### 2. docker-clean.sh
Limpeza completa:

```bash
./scripts/docker-clean.sh
```

**Remove:**
- Containers do doc2md
- Imagens do doc2md
- Volumes do doc2md
- Cache de build (opcional)

## 📁 Arquivos Modificados

### Dockerfiles
- ✅ `docker/Dockerfile.api` - Adicionado cache mount
- ✅ `docker/Dockerfile.worker` - Adicionado cache mount

### Docker Compose
- ✅ `docker-compose.yml` - Mantido para produção
- ✅ `docker-compose.dev.yml` - Novo arquivo para dev

### Scripts
- ✅ `scripts/docker-build.sh` - Build otimizado
- ✅ `scripts/docker-clean.sh` - Limpeza completa

## 🎯 Como Usar

### Primeiro Build

```bash
# Opção 1: Com script (recomendado)
./scripts/docker-build.sh

# Opção 2: Direto com docker compose
export DOCKER_BUILDKIT=1
docker compose build
```

### Rebuilds Subsequentes

```bash
# O cache será reutilizado automaticamente
docker compose build

# Ou forçar rebuild sem cache (não recomendado)
docker compose build --no-cache
```

### Desenvolvimento (Hot-Reload)

```bash
# Subir com hot-reload
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Agora você pode editar código em:
# - api/
# - workers/
# - shared/

# E as mudanças aparecem automaticamente!
```

### Produção

```bash
# Build
docker compose build

# Subir
docker compose up -d

# Ver logs
docker compose logs -f
```

### Limpar Tudo

```bash
# Limpeza completa
./scripts/docker-clean.sh

# Rebuild do zero
./scripts/docker-build.sh
```

## 🔍 Verificar Cache

```bash
# Ver cache de build
docker system df -v | grep "Build Cache"

# Ver tamanho total
docker system df
```

## 💡 Dicas

### 1. Cache de Packages
O cache de pip fica em:
```
~/.docker/buildx/cache/
```

Pode crescer bastante (1-2 GB). Para limpar:
```bash
docker builder prune -af
```

### 2. Layers de Docker
O Docker cacheia cada layer. Para máximo aproveitamento:
- ✅ COPY requirements.txt ANTES de COPY código
- ✅ Instale packages ANTES de copiar código
- ✅ Agrupe comandos RUN relacionados

### 3. .dockerignore
Certifique-se que está ignorando:
```
__pycache__/
*.pyc
.git/
tmp/
*.md
```

### 4. Desenvolvimento vs Produção

**Desenvolvimento:**
- Use `docker-compose.dev.yml`
- Hot-reload habilitado
- Volumes montados
- Mais rápido para iterar

**Produção:**
- Use apenas `docker-compose.yml`
- Código dentro da imagem
- Mais seguro e consistente

## 📈 Impacto Esperado

### Tempo de Build
```
1º build:   ~10 min  (download inicial)
2º build:   ~30 seg  (cache de packages)
3º build:   ~30 seg  (cache de packages)
...
```

### Desenvolvimento
```
Mudança no código Python:
  Antes: 10 min (rebuild completo)
  Depois: 0 seg (hot-reload)

Mudança em requirements.txt:
  Antes: 10 min (rebuild completo)
  Depois: 30 seg (reutiliza cache de alguns packages)
```

### Espaço em Disco
```
Imagens finais: ~2-3 GB (sem mudança)
Cache de build: ~1-2 GB adicional
Cache de pip: ~1-2 GB adicional

Total: ~4-7 GB (mas economiza MUITO tempo)
```

## 🎓 Como Funciona o Cache Mount

O `--mount=type=cache` permite que o Docker:

1. **Monta** um diretório persistente durante o build
2. **Preserva** o conteúdo entre builds
3. **Compartilha** entre diferentes imagens
4. **Não inclui** no resultado final da imagem

Exemplo com pip:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

Durante o build:
1. Pip baixa packages para `/root/.cache/pip`
2. Docker preserva esse cache
3. Próximo build: pip encontra packages já baixados
4. Pip instala direto do cache (muito mais rápido)
5. Imagem final não inclui o cache (menor)

## 🔧 Troubleshooting

### Build ainda lento?
```bash
# Verificar se BuildKit está habilitado
echo $DOCKER_BUILDKIT  # deve retornar 1

# Habilitar manualmente
export DOCKER_BUILDKIT=1

# Verificar cache disponível
docker system df -v | grep "Build Cache"
```

### Cache não está funcionando?
```bash
# Forçar rebuild de uma camada específica
docker compose build --no-cache worker

# Limpar cache e rebuildar
docker builder prune -af
docker compose build
```

### Espaço em disco acabando?
```bash
# Limpar cache antigo (mantém recente)
docker builder prune

# Limpar tudo (força)
docker builder prune -af

# Limpar imagens não usadas
docker image prune -a
```

## 📚 Referências

- [Docker BuildKit](https://docs.docker.com/build/buildkit/)
- [Build Cache](https://docs.docker.com/build/cache/)
- [Cache Mounts](https://docs.docker.com/build/guide/mounts/)
- [Docker Compose Override](https://docs.docker.com/compose/extends/)

## ✅ Checklist de Otimização

- [x] Cache mount em Dockerfile.api
- [x] Cache mount em Dockerfile.worker
- [x] BuildKit habilitado nos scripts
- [x] docker-compose.dev.yml criado
- [x] Scripts de build otimizados
- [x] Scripts de limpeza
- [x] Documentação completa
- [ ] Testar primeiro build (10 min esperado)
- [ ] Testar rebuild (30 seg esperado)
- [ ] Testar hot-reload em dev
- [ ] Validar cache de pip funciona
