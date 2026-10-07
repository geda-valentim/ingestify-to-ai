# Piloto live — 2026-10-05

A implementação permanece desabilitada por padrão. Este relatório registra os
replays isolados; testes automáticos/GPU não equivalem a liberação em produção.

Hardware: NVIDIA RTX 5060 Ti, 16.311 MiB; outros modelos de produção permanecem
residentes, sem pausa/restart. Antes da live: 3.985 MiB. Worker piloto: turbo,
faster-whisper 1.2.1, CTranslate2 4.8.2, torch 2.13.0+cu129; pesos
`mobiuslabsgmbh/faster-whisper-large-v3-turbo` revision
`0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`, cache local read-only/offline.

Fixture PCM PT: 240 s, mono16k s16le, SHA256
`c18f3d84b8fdee3088d2be2052c44dde563d66036a08dd61b5e732b3848a2d51`.
Não incluímos áudio nem texto das legendas no Git. O baseline existente é de máquina,
portanto não serve como ground truth/WER humano.

A API usa autenticação real, SQLite/Redis exclusivos de teste e stand-ins estritos de
MinIO/Elasticsearch que guardam todos os formatos/Markdown em disco e falham em I/O.
O decoder/modelo e os dois WebSockets são reais. Não executamos migration, deploy ou
escritas em dados de produção.

| Replay | Resultado | Primeira legenda desde captura | Atraso confirmado p95¹ | Finalização |
|---|---|---:|---:|---:|
| 30 s, aquecido inicial | Concluído; 150 frames, JSON igual aos finais WS | 0,937 s | 1,460 s | 0,539 s |
| 240 s, versão inicial | Falhou em 85,4 s por backlog >2 s | 0,768 s | 1,786 s até interrupção | — |
| 240 s, correção de contexto | Cliente abortou em 191,6 s por deadline >200 ms | 0,899 s | 1,652 s até interrupção | — |
| 240 s, aquecido 1 (API websockets 12) | Concluído; 1.200 frames; JSON igual aos finais WS | 0,831 s | 1,647 s | 0,536 s |
| 240 s, aquecido 2 (API websockets 12) | Concluído; 1.200 frames; JSON igual aos finais WS | 0,786 s | 1,648 s | 0,521 s |
| Aquecido 3 (API 12) | Cliente abortou após 579 frames por deadline >200 ms; backlog máximo 0,6 s | 0,775 s | 1,713 s até interrupção | — |
| Início frio (API 17.2) | Cliente abortou após 407 frames por deadline >200 ms; backlog máximo 0,4 s | 0,945 s | 1,632 s até interrupção | — |
| 30 s, versão final API/worker 17.2 | Concluído; 150 frames; JSON igual aos finais WS | 0,778 s | 1,493 s | 0,741 s |

¹ Timestamps do modelo, não alinhamento humano de início da fala. A primeira legenda
inclui silêncio inicial; não é uma medição desde o início real de fala.

A primeira falha revelou repetição patológica induzida pelo prompt contendo palavras
já presentes no buffer. Corrigimos o prompt para o contexto anterior ao offset,
limitamos tokens por janela e recusamos hipóteses com compressão patológica. Não
relaxamos backlog nem aceitamos texto truncado como sucesso. O segundo replay não
teve backlog excessivo até a interrupção; a janela foi invalidada pelo runner para
não enviar rajadas de catch-up.

Pico GPU observado: 6.276 MiB totais, incluindo os demais modelos residentes.
Nos dois replays de 240 s concluídos, a metadata durável registra 142,277 s e 146,755 s de
inferência (inclui extração/decodificação): RTF 0,593 e 0,611. Esses valores vêm do
contador real do decoder, não de tempo de replay/espera. A metadata antiga não gravava
compute_type, embora o worker fosse configurado CUDA/float16. A versão final envia
compute_type e contador nos eventos e no resultado. Seu replay de 30 s concluído confirmou
float16, 11,032 s de inferência, RTF 0,368 e backlog máximo 0,2 s.

O início frio do worker final mediu 8,910 s para loader+warmup e 14,379 s entre início
do restart Docker e readiness observável. A sessão só é admitida depois do modelo
pronto; primeira legenda não inclui o tempo de startup. O replay desse início frio
ficou incompleto, portanto não passa o gate de replay frio completo.

Havia cargas concorrentes de outros projetos no host. Afinidade de CPU (cliente 9, API 8,
worker 10–11) e nice=-5 no cliente/API não eliminaram todos os outliers de deadline.
A causa medida das interrupções finais foi jitter do cliente, não backlog na GPU. As
janelas foram rejeitadas pelo runner sem aumentar o limite de 2 s nem enviar catch-up.
Os dois replays completos usaram websockets 12 no harness da API; o worker usava 17.2.
A versão de dependência final é 17.2 em ambos. Isso impede afirmar que três replays
completos da versão final foram concluídos.

Ambos os resultados completos têm 527 palavras e 256 segmentos. O baseline offline
gerado por máquina tem 588 palavras e 85 segmentos. Contagem/segmentação diferente
não é uma medição de WER: requer comparação de conteúdo com referência humana antes
de afirmar equivalência/qualidade. JSON final igual aos eventos demonstra preservação
de **confirmados**, não ausência de omissões em relação ao áudio.

Gates ainda pendentes: três replays completos aquecidos e um replay completo após início frio na versão
final; corpus humano de pelo menos 20 trechos para WER/timestamps; comparação Voxtral
no mesmo corpus/configuração; concorrência planejada com workloads de produção;
integração de finalização em MySQL/MinIO/Elasticsearch reais e proxy WSS do ambiente alvo (piloto de desenvolvimento validado abaixo). Nenhum desses
gates será marcado como aprovado com base no baseline gerado por máquina.


A migração foi validada independentemente em MariaDB 10.11.13 isolado por socket,
sem rede: criação idempotente, charset/collation da FK compatíveis, generation bigint
até `2**62`, downgrade impedido com sessão ativa, preservação física dos jobs no downgrade
e CASCADE da sessão ao excluir job. Isso valida o DDL, não a finalização concorrente
em um cluster completo de storage. Rollback preserva a tabela; DROP perde a associação
SQL com a geração necessária para downloads depois do TTL.


Validação final: 1.181 testes backend passaram, três pulados; regressão adicional de busca
live cobre indexação antes do commit, cancel/DELETE/geração/owner e preserva hits de
arquivo. TypeScript, build Next de produção e seis cenários Chromium passaram. A captura
até a finalização também passou no standalone equivalente ao Docker, com o worklet
public copiado. Cinco testes do resampler/worklet cobrem 16/44,1/48 kHz e cauda.

## Piloto publicado em dev.ingestify.ai

Em 2026-10-05, ativamos explicitamente o piloto de desenvolvimento com capacidade
de uma sessão, turbo/CUDA/float16 e migration 0005 presente. O replay público
usa HTTPS/WSS pelo Cloudflare e os serviços reais MySQL, Redis, MinIO e
Elasticsearch deste servidor. Os dados de teste ficam no projeto do operador;
credenciais, áudio e texto não entram no Git.

Os primeiros replays falharam com `LIVE_BACKPRESSURE`/`LIVE_FRAME_RATE`. Profiling
mostrou a thread principal da API bloqueada em `health_check → inspect.stats →
Kombu poll`, enquanto o decoder ficava ocioso. O endpoint de saúde agora roda
no thread pool do FastAPI; limites de protocolo, fila e backlog foram preservados.
Um teste de regressão mantém a consulta Celery bloqueada e verifica que outra
requisição continua sendo atendida. Ele e os 30 testes live passaram.

| Replay público após a correção | Medida |
|---|---:|
| Áudio enviado a 1× | 30 s / 150 frames |
| Primeira legenda desde captura | 0,950 s |
| Atraso confirmado p95, timestamps do modelo | 1,517 s |
| Backlog máximo | 0,2 s |
| Tempo de inferência / RTF | 10,868 s / 0,362 |
| Finalização | 0,815 s |

A sessão emitiu `session.completed`; o JSON durável corresponde aos 32 segmentos
finais do WebSocket. Os quatro downloads JSON/TXT/SRT/VTT retornaram HTTP 200.
O fluxo de microfone no Chromium também concluiu pelo HTTPS público, com fonte
de áudio local fornecida ao dispositivo de captura do navegador: contexto seguro,
POST 201, socket WSS, 43 frames binários, dez segmentos finais e um
`session.completed`, sem erros JavaScript. O navegador executou a UI e o worklet
reais; nenhuma resposta de API foi simulada.
Este replay valida o caminho publicado e a persistência do piloto; os gates
de qualidade humana, repetição de replays longos e concorrência continuam pendentes.
