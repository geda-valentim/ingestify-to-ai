# Como Executar o Doc2MD

> **Documento histórico (out/2025) — obsoleto.** Nomes de contêiner (`doc2md-*`), portas e chamadas sem autenticação não valem mais: a API fica em `:8000` no compose base (`:8080` só com `run_api.sh` ou com o override local), há 5 réplicas de worker mais `worker-audio`, `worker-vision`, `beat` e `frontend`, e todo endpoint de negócio exige autenticação. Como subir hoje: [../README.md](../README.md), [SHARED_INFRASTRUCTURE.md](SHARED_INFRASTRUCTURE.md), [GPU.md](GPU.md) e a seção "Perfis de deploy" de [README.md](README.md).

## ⚠️ Importante: Permissão Docker

Antes de executar, você precisa adicionar seu usuário ao grupo docker.

Execute os seguintes comandos **em um terminal normal** (não aqui):

```bash
# 1. Adicionar usuário ao grupo docker
sudo usermod -aG docker $USER

# 2. Aplicar as mudanças (escolha uma opção):

# Opção A: Fazer logout e login novamente
# (mais garantido)

# Opção B: Aplicar no terminal atual
newgrp docker

# 3. Verificar se funcionou
docker ps
# Se não der erro de permissão, está ok!
```

## 🚀 Iniciar o Projeto

Após configurar permissões do Docker:

```bash
cd /var/www/doc2md

# Iniciar todos os serviços
docker compose up -d --build

# Aguardar ~30 segundos para tudo inicializar

# Verificar se está rodando
docker compose ps
```

Você deve ver 3 serviços rodando:
- `doc2md-redis` (Redis)
- `doc2md-api` (API FastAPI)
- `doc2md-worker-1` e `doc2md-worker-2` (Workers Celery)

## ✅ Testar

### 1. Health Check

```bash
curl http://localhost:8080/health
```

Resposta esperada:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "redis": true,
  "workers": {
    "active": 2,
    "available": 2
  },
  "timestamp": "..."
}
```

### 2. Documentação Interativa

Abra no navegador: http://localhost:8080/docs

Você verá a interface Swagger com todos os endpoints para testar interativamente!

### 3. Teste de Conversão

```bash
# Criar arquivo de teste
echo "# Documento de Teste

Este é um teste do Doc2MD.

## Seção 1
Conteúdo aqui.

## Seção 2
Mais conteúdo." > teste.md

# Enviar para conversão
curl -X POST http://localhost:8080/convert \
  -F "source_type=file" \
  -F "file=@teste.md"
```

Resposta:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2025-10-01T18:00:00Z",
  "message": "Job enfileirado para processamento"
}
```

### 4. Consultar Status

```bash
# Substitua JOB_ID pelo valor recebido acima
curl http://localhost:8080/jobs/JOB_ID
```

### 5. Obter Resultado

```bash
curl http://localhost:8080/jobs/JOB_ID/result
```

## 📊 Ver Logs

```bash
# Logs de todos serviços
docker compose logs -f

# Apenas API
docker compose logs -f api

# Apenas Workers
docker compose logs -f worker

# Apenas Redis
docker compose logs -f redis
```

## 🛑 Parar Serviços

```bash
# Parar containers
docker compose stop

# Parar e remover containers
docker compose down

# Parar, remover containers e volumes (limpa tudo)
docker compose down -v
```

## 🔧 Escalar Workers

```bash
# Aumentar para 5 workers
docker compose up -d --scale worker=5

# Verificar
docker compose ps
```

## 🐛 Problemas Comuns

### "permission denied" ao executar Docker

Você precisa adicionar seu usuário ao grupo docker (veja início deste documento).

### Porta 8000 já em uso

Edite `docker-compose.yml` e mude a porta:

```yaml
api:
  ports:
    - "8001:8080"  # Usar 8001 ao invés de 8000
```

Então reinicie:
```bash
docker compose down
docker compose up -d --build
```

### Serviços não inicializam

Verifique os logs:
```bash
docker compose logs
```

### Worker não processa jobs

Verifique se os workers estão rodando:
```bash
docker compose ps
docker compose logs worker
```

## 📖 Documentação Completa

- [QUICKSTART.md](QUICKSTART.md) - Guia rápido
- [README.md](README.md) - Documentação geral da API

## 🎯 Próximos Passos

1. Configurar permissão Docker (se necessário)
2. Executar `docker compose up -d --build`
3. Aguardar ~30 segundos
4. Testar health check
5. Abrir http://localhost:8080/docs
6. Fazer upload de um arquivo de teste
7. Consultar status e resultado

Pronto! Sua API de conversão de documentos para Markdown está funcionando! 🚀
