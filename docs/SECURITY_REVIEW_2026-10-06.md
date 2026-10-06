# Revisão de segurança — 2026-10-06

Escopo: correções dos achados de [SECURITY_REVIEW.md](SECURITY_REVIEW.md),
revalidação dos controles históricos de [CODE_REVIEW.md](CODE_REVIEW.md),
dependências, segredos no Git e configuração para disponibilizar o projeto como
open source. Base: `origin/main` em `f9dd437`, branch `fix/oss-security-hardening`.
Três agentes GPT-6.1 Sol implementaram e revisaram admissão, autenticação e
infraestrutura; o integrador verificou dependências do frontend e integração.
Não foi realizado pentest externo nem alterada a visibilidade do repositório.
A consulta atual ao GitHub (`gh repo view --json visibility`) retornou **PUBLIC**: o
histórico já está público. Os gates de CI sinalizam pendências de release; não
impedem acesso ao Git nem substituem contenção das exposições existentes.

## Achados anteriores

| Achado | Correção e evidência | Limite |
| --- | --- | --- |
| S-01: JWT enviado a provedores | Mantida a separação `Authorization` / `X-Source-Token`; token externo fica no Redis com TTL e não entra no Celery. Testes de fontes e conversão verificam esse contrato. | O provedor ainda recebe seu próprio token por HTTPS. |
| S-02: jobs sem orçamento | `shared/job_admission.py` reserva uma linha SQL antes de ler/processar/enfileirar trabalho no handler, serializada pelo usuário. API keys e JWT compartilham identidade. Redis limita criação; dependências indisponíveis retornam 503. | Orçamento cobre entrada retida/projetada, não o volume total de resultados derivados. |
| S-03: login falha aberto / identidade do proxy | Reservas atômicas antes de bcrypt, Redis indisponível retorna 503 e nenhum token é emitido se a limpeza falhar. Identidade vem do peer ASGI validado pelo Uvicorn. | Implantação deve configurar IPs exatos e substituir headers no ingress. |
| S-04: infraestrutura sem proteção obrigatória | Overlay de produção exige TLS com CA/hostname e credenciais Redis, Elasticsearch e MinIO; remove portas públicas da infraestrutura e separa volumes/rede de dev. | Certificados, credenciais e ingress precisam ser provisionados; o dev existente não foi migrado. |

Admissão cobre upload, conversão local/remota, transcrição, quatro endpoints de
imagem, live e retry de páginas. Reservas abandonadas expiram; trabalho
persistido não perde sua vaga por TTL. Retry automático conserva o estado
pendente até esgotar as tentativas. Excluir trabalho ativo retorna 409;
exclusão e retry disputam o mesmo lock. Remover a entrada no MinIO deve ser
confirmado antes de excluir o registro SQL: falhas retornam 503 e mantêm a cota. O splitter limita fan-out de PDFs antes
de extrair páginas. Downloads Drive/Dropbox gravam em disco com limite de bytes,
sem acumular o arquivo inteiro em memória e sem deixar parciais em erro.

Padrões: 20 criações/minuto, 4 jobs ativos, 1.000 retidos, 1 GiB de entradas,
600 segundos para reserva provisória e 500 páginas no splitter. Live reserva o
máximo PCM permitido; imagens reservam seu limite próprio. Todas essas opções
estão em `.env.example`. Os limites existentes de tarefa/arquivo continuam
necessários; não há promessa de isolamento rígido de CPU/GPU ou de quota física
para todos os outputs. Órfãos de falhas entre upload e commit SQL, versões
antigas em buckets versionados e resultados derivados exigem limpeza/retenção
operacional; não estão cobertos por uma quota física de armazenamento.

IDOR de jobs/páginas, endpoints admin, CORS explícito, ausência de segredo JWT
padrão, bucket privado e defesa SSRF foram reavaliados com seus testes existentes.
Os achados antigos de `CODE_REVIEW.md` permanecem históricos. JWT no localStorage
continua aumentando o impacto de XSS; esta mudança não migra sessões para cookies.

## Novos achados e dependências

O frontend tinha dependências com advisories, incluindo PDF.js vulnerável.
Foi atualizado para Next.js 16.3.8, React-PDF 11/PDF.js 6.3.289 e Tailwind 4.3.3,
com lockfile e `npm ci`. O worker de PDF e seus decodificadores, CMaps e fontes
são servidos pela aplicação; não se executa um worker vindo de CDN. O build usa
Node 24 e o container final continua sem root. Contextos Docker excluem arquivos
locais de ambiente e artefatos de desenvolvimento.

O backend atualiza parsers HTTP/formulários, Docling, Pillow e dependências de
autenticação; PyJWT substitui python-jose e pypdf substitui PyPDF2. Tokens HS256
existentes continuam válidos. Consulte a matriz e a análise de alcance em
[security-python-dependencies.md](security-python-dependencies.md).

**WhisperX e Diart continuam com advisories sem resolução compatível.** O código
recusa esses runtimes em produção, inclusive seleção por perfil/job, cache,
entrada direta e execução remota. O bloqueio não corrige as bibliotecas.
faster-whisper permanece disponível. Testes locais de WhisperX exigem ambiente
de desenvolvimento explícito; liberar produção exige dependências corrigidas e
nova qualificação de inferência.

## Histórico e publicação

A varredura de todos os refs identificou uma API key histórica e material
criptográfico gerado em builds antigos do Next.js. A API key não corresponde a
nenhuma linha no banco do dev inspecionado; os 13 valores criptográficos distintos
também não coincidem com os manifests do frontend em execução. Isso não comprova
revogação em outras instalações. Valores não foram incluídos neste relatório.

Como o Git já está público, é necessário confirmar o escopo das instalações
e invalidar qualquer uso remanescente das credenciais expostas. Histórico não foi reescrito; exposições
reais não devem ser silenciadas como falsos positivos. A triagem e os gates de CI
ficam em [security-history-review.md](security-history-review.md).

## Validação

- MariaDB 11.4 real, InnoDB REPEATABLE READ: 5 testes passaram, cobrindo 16
  admissões simultâneas para 4 vagas, expiração/rollback e ambos os vencedores
  da disputa entre exclusão e retry.
- Redis real: 12 requisições concorrentes para 3 tentativas admitiram exatamente
  3 e rejeitaram 9 com 429; TTL confirmado. Testes HTTP usam o middleware real
  de proxy e incluem headers falsificados e indisponibilidade de Redis.
- Serviços TLS isolados: Redis autenticado respondeu PONG; Elasticsearch
  autenticado respondeu 200 e anônimo 401; MinIO respondeu health 200 e anônimo
  403. Certificados não confiáveis e transporte plaintext foram rejeitados.
- Compose efetivo inspecionado com overlays de produção/GPU/live/engines;
  sem portas da infraestrutura ou mounts de código de desenvolvimento.
- Frontend: typecheck e build de produção passaram; build Docker com `npm ci`
  passou e o container respondeu como UID 1001. Navegador Chromium renderizou
  PDF com JPEG2000, verificando pixels do canvas, worker local e OpenJPEG WASM
  com HTTP 200, sem erros JavaScript. Layout de docs e job inspecionado em
  1440 e 390 pixels. Não é uma prova de equivalência visual de todas as telas.
- Auditorias npm e dos conjuntos Python padrão/vision/live padrão/remote
  não encontraram advisories nas resoluções verificadas. Os conjuntos opcionais
  WhisperX/Diart permanecem explicitamente sinalizados.

Os testes leves usam `backend/requirements-test.lock` com hashes; não substituem
qualificação de modelos CPU/GPU. Containers de validação são descartáveis.
A suíte backend completa passou: **1.384 testes, 7 skips, 27 avisos** em ambiente
limpo Python 3.11 com dependências do lock. A mesma suíte passou também em
Python 3.13: **1.378 testes, 7 skips** antes das seis regressões finais de
exclusão; depois delas, 50 testes dirigidos passaram também em 3.13. Imports reais API/Dropbox/pydub/faster-whisper
passaram; `audioop-lts` condicional corrige a remoção de `audioop` no Python 3.13. Cinco skips correspondem aos testes
MariaDB executados separadamente; dois exigem a infraestrutura externa de
concorrência dos engines. Não há alegação de deploy ou de ambiente público seguro.

Operação de produção: [runbook](runbooks/production-infrastructure.md) e
[contrato de autenticação/ingress](security-auth-ingress.md). Imagens de base
mutáveis e resoluções Python fora dos locks continuam exigindo auditoria no
build. Também falta definir uma licença do repositório antes de apresentá-lo
como open source; nenhuma licença foi escolhida em nome dos responsáveis.
