# 0011 — Full Analysis para imagens

| | |
|---|---|
| **Status** | Implementada; ativação facial opt-in |
| **Autor** | Codex, a pedido de Geda Valentim |
| **Criada em** | 2026-10-06 |
| **Atualizada em** | 2026-10-06 |
| **Relacionadas** | [0003](0003-motores-de-execucao-roteamento-e-orcamento.md), [0012](0012-deteccao-facial-e-expressoes.md) |
| **Substituída por** | — |
| **Revisão técnica** | Agente `full_analysis_review`, 2026-10-06: revisão focada e rechecagem; achados corrigidos, sem bloqueios concretos nos pontos revisados |

## 1. Problema

Na análise de imagens, o usuário escolhe uma tarefa Florence-2 por vez: descrição,
OCR, detecção, segmentação etc. Ele quer uma opção **Full Analysis** que receba
uma imagem e entregue juntas todas as análises de visão suportadas, sem precisar
submeter a imagem repetidamente e reunir os resultados manualmente.

O workspace já tem 15 tarefas em `shared/vision_capabilities.py`, entradas
validadas em `ImageAnalyzeOptions`, `/images/analyze` e `/images/analyze/upload`,
worker Florence-2 e visualização de caixas/polígonos. Cada solicitação executa
uma tarefa. Esta spec acrescenta um modo composto nesse mesmo fluxo de imagens.

## 2. Objetivo

Adicionar a opção **Full Analysis** ao formulário e à API de imagens, executando
as 15 capacidades disponíveis em uma execução composta e devolvendo um relatório
com descrições, texto, objetos, regiões e segmentações, mais cobertura por tarefa.

O modo funciona com a imagem sozinha. Entradas de tarefas condicionadas são
resolvidas automaticamente a partir das descrições/detecções iniciais. O usuário
pode fornecer objetos/frases e regiões de interesse nas opções avançadas.

### Fora de escopo

- Áudio, vídeo, documentos e agregação de conversas/clientes.
- Novo serviço genérico de análises ou novos perfis de execução de engines.
- Introduzir outros modelos, LLM para síntese ou capacidades fora do catálogo de visão
  no perfil `image-full-v1`; a extensão facial v2 é proposta separadamente na [0012](0012-deteccao-facial-e-expressoes.md).
- Executar todas as combinações de parâmetros ou segmentar cada pixel/objeto possível.
- Identificação civil de pessoas, diagnóstico ou inferência de atributos sensíveis.

## 3. Critérios de aceitação

- [x] Uma imagem enviada com `mode=full`, sem prompts/regiões adicionais, gera
  um único job MAIN de imagem e um relatório composto consultável por seu ID.
- [x] A opção aparece no formulário ao lado das operações existentes, com uma
  explicação das entregas e do processamento adicional.
- [x] As oito tarefas sem entrada adicional são executadas e preservadas separadamente.
- [x] As sete tarefas condicionadas usam texto/regiões resolvidos, com origem
  explícita; ausência de candidato válido é reportada, sem inventar objetos.
- [x] Há cobertura das 15 famílias e de cada instância resolvida; nenhuma falha,
  indisponibilidade ou corte de execução recebe selo de análise integral.
- [x] OCR vazio/detecção vazia são resultados válidos, distintos de erro.
- [x] Request JSON e multipart têm as mesmas regras; operações individuais
  continuam com os contratos atuais quando `mode` for omitido ou `single`.
- [x] Descrições, linhas de OCR, caixas e polígonos podem ser visualizados por
  camada sobre a imagem, em coordenadas da mesma imagem decodificada.
- [x] Relatório e etapas concluídas sobrevivem a F5, expiração do Redis e
  redelivery; repetir a mesma criação idempotente não executa outro lote.
- [x] Timeout/falha parcial preservam resultados úteis, com estado parcial e
  custos/tempos reais do lote; sucesso exige persistência durável do relatório.

## 4. Solução proposta

### 4.1 Uma opção composta, com resolução automática de entradas

`mode=full` é uma opção de orquestração. Não criar um token nativo
`<FULL_ANALYSIS>` nem adicioná-lo ao `VisionTask` do Florence.

**Primeira fase:** executar as oito tarefas independentes sobre a imagem:

| Tarefa | Entrega |
|---|---|
| `<CAPTION>` | Descrição breve |
| `<DETAILED_CAPTION>` | Descrição detalhada |
| `<MORE_DETAILED_CAPTION>` | Descrição muito detalhada |
| `<OCR>` | Texto extraído |
| `<OCR_WITH_REGION>` | Texto, linhas e quadriláteros |
| `<OD>` | Objetos e caixas |
| `<DENSE_REGION_CAPTION>` | Descrições de regiões e caixas |
| `<REGION_PROPOSAL>` | Propostas de regiões |

**Segunda fase:** resolver entradas e executar as sete tarefas condicionadas:

| Tarefa | Entrada automática | Entrega |
|---|---|---|
| `<CAPTION_TO_PHRASE_GROUNDING>` | Descrição muito detalhada; fallback descrição detalhada/breve | Frases localizadas na imagem |
| `<OPEN_VOCABULARY_DETECTION>` | Até três labels/descrições distintas da detecção; fallback caption | Objetos por vocabulário aberto, por consulta |
| `<REFERRING_EXPRESSION_SEGMENTATION>` | Mesmas consultas resolvidas | Polígonos por expressão |
| `<REGION_TO_SEGMENTATION>` | Regiões resolvidas | Polígonos por região |
| `<REGION_TO_CATEGORY>` | Regiões resolvidas | Categoria da região |
| `<REGION_TO_DESCRIPTION>` | Regiões resolvidas | Descrição da região |
| `<REGION_TO_OCR>` | Regiões resolvidas | Texto da região |

Resolução padrão de regiões: incluir a imagem inteira `[0,0,1,1]` e até três
caixas válidas detectadas/propostas. Ordenar origens OD → dense captions →
region proposals, por score quando disponível e ordem original como desempate.
Converter pixels para coordenadas normalizadas, validar área/limites e eliminar
caixas equivalentes com IoU ≥ 0,85; a imagem inteira fica separada desse dedupe.
Registrar candidatos considerados, selecionados e omitidos pelo limite.

Consultas são labels de OD, depois descrições de dense captions, sem duplicatas
após normalização de espaços; se vazias, usar a primeira caption não vazia.
Não usar um parser/LLM adicional para inventar perguntas. Grounding recebe uma
caption resolvida. Cada consulta/região recebe ID estável e origem
`user`, `caption`, `object_detection`, `dense_region_caption`,
`region_proposal` ou `full_image`, com referência ao resultado que a originou.

Consultas/regiões explícitas substituem os candidatos automáticos daquele grupo.
Sem caption/consulta válida, tarefas textuais ficam `not_applicable` com
`no_valid_text_input`; se isso ocorrer por falha de todas as dependências,
ficam `skipped/dependency_failed`, tornando a análise parcial. A imagem inteira
continua sendo região válida mesmo quando nenhum objeto é detectado.

Limites do perfil `image-full-v1`: até três consultas, quatro regiões no total,
2000 caracteres por texto e 32 chamadas nativas. Com máximos padrão:
`8 + 1 grounding + 3 vocabulary + 3 expression + 4×4 region = 31 chamadas`.
Textos automáticos acima do limite são recortados em limite de frase quando
possível, com `input_truncated=true` e o texto efetivamente usado registrado.
Uma saída com tokens esgotados é marcada truncada; não anunciar OCR/descrição
integral para uma saída interrompida pelo limite.
Estender o helper de geração para preservar contagem de tokens efetivamente
gerados, EOS e `finish_reason=stop/length/deadline/cancel/error` antes do
pós-processamento. `length` significa limite atingido sem EOS normal; não inferir
truncamento só pelo tamanho do texto. Esses metadados acompanham cada resultado.

A cobertura integral refere-se às tarefas e instâncias do perfil limitado,
não a todos os objetos que poderiam existir na imagem. Mostrar alcance escolhido,
candidatos omitidos e o limite. A amostragem de regiões não fica oculta.

### 4.2 API e compatibilidade

Reusar as rotas atuais, com JWT ou API key e ownership SQL:

| Método | Rota | Mudança |
|---|---|---|
| POST | `/images/analyze` | União entre opções single atuais e `mode=full` |
| POST | `/images/analyze/upload` | Novo campo `mode` e JSON `full_options` |
| GET | `/images/capabilities` | `analysis_modes`, perfil full, tarefas e limites resolvidos |
| GET | `/jobs/{id}` | Progresso do lote, contagens de etapas e estado terminal parcial |
| GET | `/jobs/{id}/result` | Envelope existente, com resultado de imagem composto |
| POST | `/images/{job_id}/cancel` | Nova rota, somente jobs full do dono; pedido idempotente de cancelamento |

Exemplo de request JSON:

```json
{
  "image_base64": "BASE64_DA_IMAGEM",
  "filename": "foto.png",
  "project": "Imagens",
  "mode": "full",
  "wait": false
}
```

Exemplo com opções avançadas:

```json
{
  "mode": "full",
  "full_options": {
    "queries": ["a red car", "a person"],
    "regions": [[0.1, 0.2, 0.8, 0.9]],
    "generation": {"max_new_tokens": 1024, "num_beams": 3},
    "deadline_seconds": 900
  }
}
```

O segundo exemplo mostra apenas as opções; imagem/localização seguem o primeiro.
`queries`/`regions` omitidos ativam resolução automática; listas vazias são 422.
Grounding usa queries explícitas concatenadas com separador `. ` quando fornecidas,
substituindo a caption automática; caso contrário usa a caption resolvida.
Limite de 2000 caracteres: rejeitar concatenação acima dele antes de
criar job. `generation` reusa `VisionGenerationOptions` e é resolvido/fixado no
job; não variar modelo/parâmetros entre etapas sem opção explícita.

Sem `mode`, manter o parser single atual. Full rejeita `task`, `text_input`,
`region` e `generation` de single quando explicitamente enviados; seus parâmetros
ficam em `full_options`. No multipart, verificar presença real do campo para
não confundir o default implícito de `task` com um envio explícito incompatível.
Campos desconhecidos são 422. Projeto/pasta/tags seguem o contrato existente
da submissão e ficam vinculados ao mesmo job.

As rotas atuais de imagem ainda não vinculam destino datalake. Acrescentar,
no branch full do request, `datalake: Destination` opcional conforme
`shared/datalake/schemas.py`: `connection_id`, `bucket`, `prefix`, `partitioning`
e `partition_values`. Multipart full usa um campo `datalake` contendo o mesmo
objeto JSON. Validar dono da conexão/bucket permitido e executar
`bind_destination` na transação do job, congelando o snapshot conforme a
[0008](0008-particionamento-configuravel-datalakes.md). Ausente significa sem
exportação; não ampliar silenciosamente o contrato single nem herdar um destino
sem escolha explícita. A integração do resultado composto ao exporter também
faz parte desta entrega, não é funcionalidade de imagem já existente.

Header `Idempotency-Key` obrigatório somente para full, único por dono/operação.
Mesmo conteúdo/hash/opções/localização/destino retorna o mesmo job; mesma chave
com payload diferente retorna 409. Vincular chave e job atomicamente e preservar
replay enquanto o job existir. Após exclusão, conservar tombstone da chave por
24h e retornar 410, sem executar novamente por efeito de retry atrasado.

Resposta padrão 202 com `job_id`, `status=pending`, `poll_url` e `result_url`.
`wait=true` segue o prazo de espera HTTP existente: pode retornar resultado
terminal tipado ou 504 com os mesmos IDs/URLs; a execução continua. 504 não
cancela o lote e não autoriza o frontend a reenviar a imagem automaticamente.
A resposta síncrona full tem schema próprio, sem fingir `task: VisionTask` único.
Cancelamento é novo neste incremento: persistir flag SQL; 202 para pedido em
andamento e 200 com estado atual se já terminal. Verificar job/configuração full
e ownership, sem habilitar cancelamento para outros tipos. Impedir novas etapas,
sinalizar a inferência em voo e terminar como cancelled preservando checkpoints;
pedido não promete interromper instantaneamente uma operação já iniciada.

Erros: 401 auth; 404 job de outro dono; 409 idempotência; 410 replay de job
excluído; 413 bytes; 422 formato/pixels/opções; 503 visão/engine indisponível;
504 espera HTTP. Ausência de uma capacidade específica é lacuna reportável;
modelo incapaz de iniciar o lote é rejeitado antes de criar job.

### 4.3 Resultado e interface

`image.operation=full_analysis` discrimina um novo `ImageFullAnalysisResult`,
sem alterar o formato de imagem single. Ele inclui `schema_version`, perfil,
modelo/revisão, dimensões, hash, opções efetivas, entradas resolvidas, cobertura,
resultados nativos, duração total e referências dos artefatos. Cada item tem
`step_id`, tarefa nativa, input resolvido, estado, duração, output bruto e
`text/regions/lines` normalizados com os helpers existentes.

Exemplo reduzido do bloco full, com demais resultados omitidos apenas no exemplo:

```json
{
  "operation": "full_analysis",
  "schema_version": "image-full-result-v1",
  "profile": "image-full-v1",
  "analysis_status": "partial",
  "coverage": {
    "task_families_total": 15,
    "task_families_completed": 14,
    "instances_planned": 31,
    "instances_completed": 30
  },
  "results": [{
    "step_id": "ocr",
    "task": "<OCR>",
    "status": "succeeded",
    "text": "TOTAL 42.00",
    "output": "TOTAL 42.00",
    "regions": [],
    "duration_ms": 1200
  }]
}
```

Estados por etapa: `pending/running/succeeded/failed/skipped/not_applicable`.
Família só completa se todas suas instâncias previstas terminarem com sucesso
ou forem realmente inaplicáveis. Falha, dependência quebrada, deadline,
capacidade indisponível ou truncamento não são inaplicabilidade. Um output vazio
válido de OCR/detecção conta como resultado disponível. `failed` exige ausência
de qualquer etapa com resultado válido, ou falha estrutural que impeça persistir
o envelope; resultados válidos com lacunas produzem `partial`.

Adicionar `JobStatus.PARTIAL`, apenas usado pelo novo modo quando houver lacunas.
Atualizar schemas, filtros/contagens e UI para esse estado. `completed` exige
cobertura integral das instâncias resolvidas e relatório durável. Cancelamento
usa o estado existente; resultados já persistidos ficam acessíveis. Resultado
terminal failed/partial/cancelled tem envelope com cobertura/erros mesmo vazio;
202 fica exclusivo de execução em andamento.

Formulário: opção **Full Analysis** com “Descrições, texto, objetos, regiões e
segmentações em uma execução”. Imagem basta; inputs avançados são opcionais.
Resultado: descrição geral, três captions, OCR, objetos, regiões, grounding e
segmentações em abas/seções; seletor de camadas/instâncias impede empilhar todos
os polígonos de uma vez. Descrição geral usa MORE_DETAILED_CAPTION, com fallback
identificado. Não adicionar síntese semântica independente.

Mostrar progresso “etapa X de Y”, cobertura das 15 tarefas, escopo das consultas/
regiões e limitações. Overlay e recortes usam coordenadas de uma imagem única,
com orientação/normalização congelada; saída original do modelo permanece
consultável. Exportar JSON completo e relatório Markdown derivado dele; imagem
original aparece uma vez no envelope, sem base64 repetido por etapa.
Fixar o bitmap analisado e suas dimensões, inclusive EXIF e primeiro frame de
GIF/TIFF conforme o decoder. Preview deve usar esse mesmo bitmap, não aplicar
outra rotação do browser; indicar explicitamente quando só um frame foi analisado.

### 4.4 Worker, persistência e limites

Fluxo: API valida → SQL cria job/configuração/chave idempotente → persiste imagem
original privada → outbox enfileira lote → worker executa fases em sequência →
checkpoint de cada etapa → relatório durável → estado terminal e entrega opcional.

Reusar fila `VISION_QUEUE`, provider e modelo residente. Uma task dedicada ao
lote evita que cada tarefa nativa crie outro job ou apague a imagem temporária.
Abrir/decodificar imagem uma vez por execução; manter pesos residentes. Não
encadear os endpoints HTTP e não chamar o worker single que conclui o job e
limpa o arquivo a cada inferência. Extrair execução nativa sem esses efeitos.

Adicionar tabelas mínimas com migration explícita: `image_analysis_steps`
(job, step_id único, tarefa, input/hash, estado, lease/fence, tentativas,
resultado/checksum/caminho e tempo); `image_analysis_submissions` (dono/chave
únicos, hash, job/tombstone); e outbox de submissão full se não houver mecanismo
SQL compatível reutilizável. Etapas da segunda fase são resolvidas e persistidas
atomicamente uma vez; recuperação usa essas entradas, sem recalcular candidatos.
Defaults/modelo/revisão/perfil e toda configuração efetiva ficam em JobConfiguration.
Persistir `calls_started` do lote com incremento atômico antes de cada inferência,
incluindo chamadas de recuperação e chamadas que morram sem output. Reservar
contador e lease/fence juntos; uma tentativa incerta não devolve esse crédito.
Nunca exceder 32: se 31 chamadas já começaram, sobra apenas uma tentativa de
recuperação, não uma por etapa. Esgotamento gera lacuna `call_limit`, sem iniciar
nova inferência. Mostrar tentativas e chamadas separadas de etapas úteis concluídas.

Imagem original vive em `images/{job_id}/source` no bucket privado. Checkpoints
usam chaves imutáveis `images/{job_id}/steps/{step_id}/{fence}-{sha256}.json`;
relatórios full usam `images/{job_id}/reports/{fence}-{sha256}.json`. SQL aponta
à versão publicada; `jobs.minio_result_path` aponta ao relatório final vencedor,
sem alterar o path dos jobs single. Verificar escrita/checksum antes do commit
condicional que exige fence atual e job ainda ativo. Um writer antigo não
sobrescreve checkpoint/relatório publicado; objetos órfãos são coletados.
Falha de MinIO não pode produzir completed só no Redis.
Leitura começa autorizando pelo SQL. Redis é cache com TTL, inclusive progresso.
Excluir job remove fonte, checkpoints, relatório e estado idempotente conforme
retenção de tombstone; nenhum cleanup temporário apaga a fonte de lote ativo.
Excluir job primeiro invalida lease/publicação no SQL e registra purge em outbox,
para um worker em voo não ressuscitar objetos ou resultados depois da exclusão.

Full usa timeout próprio, separado do `VISION_TASK_TIMEOUT_SECONDS` single:
`VISION_FULL_TASK_TIMEOUT_SECONDS=900`, máximo de request 900 segundos na primeira
versão. Deadline começa na admissão e inclui fila/carga/inferência/persistência.
Ao iniciar, calcular prazo restante e usá-lo como timeout efetivo de execução;
fila de 300s deixa no máximo 600s de execução, não mais 900s. Se já vencido,
não carregar modelo/iniciar inferência. Soft limit reserva margem de persistência.
Dentro de generate, stopping criteria checa deadline/cancelamento entre tokens;
timeout/supervisor do processo também cobre carga ou chamada nativa travada.
Watchdog vence lease/fence e fecha envelope pelo checkpoint ao atingir o prazo,
sem aceitar publicação tardia como sucesso. Medir qualquer computação residual
até confirmação do término; não declarar custo zero porque o deadline expirou.
Não habilitar o modo sem teste de fila + inferência travada comprovando esse gate.

Lease/fencing SQL por lote e publicação condicional por etapa evitam duas
publicações. Redelivery reutiliza checkpoints verificados e executa só etapas
pendentes. Não retentar automaticamente falha de inferência; uma recuperação de
crash admite no máximo uma nova tentativa por etapa incerta, respeitando prazo,
nova admissão/claim de reserva e teto global de 32 chamadas. Registrar tentativa
anterior e medir consumo de recuperação separadamente. Não expor retry que recrie silenciosamente
um job ou esconda custo duplicado. Nova solicitação explícita usa nova chave.

Com rota de engine, reservar/claim/heartbeat/settle o lote inteiro em uma execução
vision_request, considerando limite de chamadas e duração máxima, sem liquidar
cada etapa como o job inteiro. Perda de claim não permite executar o lote fora
do accounting pelo fallback do worker single: recusar e reconciliar. Consumo de
recuperação é contabilizado; modelo/revisão congelados não mudam em fallback.
Revalidar claim/lease e prazo antes de cada chamada e antes de publicar o
resultado. Perder claim durante o lote interrompe novas etapas; a inferência já
em voo pode terminar, mas seu checkpoint só é adotado por reconciliação e fence
válido. Não liquidar sucesso nem publicar estado terminal como titular antigo.
Uma redelivery com outro titular ainda ativo sai sem iniciar outra execução.
Primeira versão atende apenas o provider/adapters de visão já qualificados;
nenhum envio novo a serviço/modelo externo é introduzido por esse modo.

Destino opcional usa o novo binding full e reusa o contrato de snapshots/partições
dos datalakes; exporta o envelope composto e seu relatório. Entrega deve reconhecer partial como terminal com
resultado útil, preservando `analysis_status` na exportação e no dataset, sem
representar partial como sucesso integral. Falha de entrega fica separada da
inferência. Docs de endpoints e guias PT/EN só anunciam disponibilidade após
implementação/qualificação.

## 5. Alternativas consideradas

| Alternativa | Decisão |
|---|---|
| Full como uma caption longa | Não entrega OCR, objetos, caixas/polígonos nem as demais saídas |
| Cliente enviar 15 requests | Obriga a coordenação/reenvio e fragmenta jobs e resultados |
| Executar só as oito tarefas sem entrada | Não cobre as funções condicionadas; resolver inputs automaticamente |
| LLM adicional gerar relatório | Adiciona dependência/custo sem necessidade para reunir saídas de visão |

## 6. Impactos

- Compatibilidade: modo single preservado; union de resposta e estado partial
  são aditivos, restritos aos jobs criados pela nova opção.
- Performance: até 31 inferências por imagem no perfil inicial; consumo e
  latência maiores, fila assíncrona e deadline explícitos, sem estimativa fictícia.
- Segurança: mesma autorização SQL, limites de imagem/inputs e armazenamento
  privado; labels/captions são dados, não instruções nem gatilho para ações.
- Operação: timeout de lote, checkpoints/outbox e métricas por tarefa e lote;
  worker ocupado continua publicando heartbeat.
- Custo: reserva do lote e recuperação contabilizadas; tempos reportados não
  são promessa de preço/latência nem prova de precisão do modelo.

## 7. Plano de testes

- Unitários: catálogo com 8+7 tarefas, resolução determinística de inputs,
  conversão/dedupe de caixas, limites 3/4/32, inputs vazios e status/cobertura.
- API: JSON/multipart parity, mode omitido/single, campos incompatíveis, geração,
  projeto/pasta/tags/destino, idempotência e isolamento de donos.
- Integração: todas as 15 tarefas com provider fake; checkpoint/redelivery,
  outbox, MinIO/Redis fora do ar, crash após objeto antes de SQL, timeout/cancel,
  lease perdido antes/durante o lote, writer tardio, accounting, contador32
  incluindo recovery, partial export, cancelamento e exclusão de job.
- Deadline/truncamento: fila + chamada travada, prazo restante no início,
  tokens/EOS/finish_reason, stopping criteria e finalização por watchdog.
- Inferência real: imagem com objetos/texto, imagem sem texto/objetos e inputs
  avançados; verificar todas as famílias, geometria, candidatos e truncamento.
- Frontend automatizado: selecionar Full Analysis, enviar, ver progresso,
  abas/camadas, resultado parcial, F5/Redis expirado e exportações.
- Documentação: schemas/OpenAPI/referência gerada e exemplos consistentes.

## 8. Plano de implementação

- [x] PR1 — Schemas/mode/catálogo, planner 8+7 e contrato composto de resultado.
- [x] PR2 — Status partial, checkpoints/idempotência/outbox e imagem durável;
  cancelamento full e integração com ledger sem efeitos terminais das tarefas single.
- [x] PR3 — Worker full com fases automáticas, recuperação/deadline e exportações.
- [x] PR4 — Opção no front, visualização por camada, docs e qualificação real.

## 9. Decisões e revisão

- [x] Escopo → **Decisão (2026-10-06):** uma opção Full Analysis para imagens,
  conforme correção do usuário; a proposta anterior multimídia foi reescrita.
- [x] Precisa preencher sete tarefas manualmente? → **Decisão:** imagem basta;
  captions/objetos/regiões iniciais alimentam as tarefas condicionadas.
- [x] Como evitar fan-out infinito? → **Decisão:** perfil versionado com até
  três consultas/quatro regiões e teto de 32 chamadas, com alcance visível.
- [x] Novo endpoint/serviço genérico? → **Decisão:** modo composto nas rotas
  atuais de imagens, com um job e um resultado.
- [x] Revisão focada em imagens → **Concluída (2026-10-06):** catálogo 8+7 e
  fan-out 31 conferidos no código; corrigidos deadline incluindo fila/inferência,
  perda de claim durante lote, teto de tentativas, integração datalake aditiva,
  evidência de truncamento, resultado vazio válido e precedência do grounding.
  Rechecagem confirmou as correções, sem bloqueios concretos nesses pontos.

Verificação documental: exemplos JSON, links locais, seções do template e
presença das 15 tarefas do catálogo validados. Os critérios de aceitação seguem
pendentes de implementação; a revisão não altera o status **Rascunho**.

## 10. Implementação e qualificação (2026-10-06)

Implementada na branch `feat/image-full-analysis`; pedido de implementação autorizado pelo usuário.

- API JSON/multipart `mode=full`, opções tipadas, chave idempotente e cancelamento próprio.
- Planner 8+7 com entradas automáticas/avançadas e limite de 32 chamadas.
- SQL/MinIO duráveis, fences/checkpoints, outbox, prazo desde admissão, purge confirmado e leitura sem Redis.
- Ledger por lote e reconciliação de crash com medição ausente marcada explicitamente.
- Frontend desktop/celular: opções, cobertura, camadas, resultados parciais, downloads e F5.
- Referência gerada: 146 endpoints e 184 schemas; guias de visão PT/EN atualizados.
- Revisão do agente `full_analysis_review`: três rodadas de implementação; achados corrigidos, sem bloqueios adicionais na revisão final.

Validações executadas:

- 387 testes de backend passaram: 384 de regressão (API, visão, full, projetos, datalakes, particionamento, engines e documentação), mais 2 de EOS/truncamento/reuso do bitmap e 1 de auditoria de candidatos/limites de texto. A execução final dos 58 testes de full e visão passou após os últimos ajustes.
- TypeScript e build de produção passaram. Browser full passou em 1440×1100 e 390×844, incluindo resposta perdida e chave conservada; repetido no frontend publicado.
- `backend/tests/image_full_deadline_probe.py`: prefork real, espera de 2.5s na fila, inferência que ignora soft signal, hard kill em 6.7s de prazo total 6s (arredondamento do timer), watchdog preservando diagnóstico das 15 famílias. SQL/storage/fila isolados.
- `backend/tests/image_full_real_probe.py`: Florence-2-base-ft fixado no commit configurado, CUDA, tokens 64/beams 1, sem download. Cenário automático: 15/15, 29 chamadas; consultas/regiões explícitas: 15/15, 31; imagem em branco: 15/15, 15. Zero falhas/truncamentos nesses exemplos; PNG canônico 320×240 sem rotação EXIF adicional.
- Migração aditiva aplicada no dev; API, workers, beat e frontend atualizados.

Esses resultados qualificam o fluxo e seus contratos. Não são promessa de precisão semântica para qualquer imagem ou de cobertura de todas as combinações de consultas/regiões/parâmetros.

Smoke adicional no dev: envio multipart real → MySQL/MinIO → Celery/engine → Florence CUDA → leitura normal e JSON. Concluiu 15/15 em 25 chamadas; reenvio idempotente devolveu o mesmo job. Usuário, projeto, job e objetos sintéticos foram removidos ao terminar.

## 11. Extensão planejada — rostos e expressões

A [spec 0012](0012-deteccao-facial-e-expressoes.md), **implementada**, acrescenta
uma operação específica de análise facial e sua integração ao Full Analysis.
Esta seção registra a extensão implementada; a qualificação acima corresponde
exclusivamente ao perfil `image-full-v1` já implementado.

- Novo perfil `image-full-v2`: as 15 famílias Florence e três famílias faciais
  (`face_detection`, `face_movements`, `face_expression_classification`).
- Seleção explícita por `full_options.profile`; omissão mantém v1. O v2 inclui
  faces por padrão, aceita `full_options.faces` e até cinco rostos selecionados.
- MediaPipe fornece detecção/geometria/blendshapes; EmotiEffLib fornece classes
  estimadas de expressão. Modelos e pesos exigem qualificação própria.
- Resultado `image-full-result-v2` com etapas discriminadas por provider/tipo,
  bloco facial por rosto, lista de modelos e cobertura das 18 famílias.
  Não adicionar tarefas faciais ao enum nativo `VisionTask`.
- Teto por lote v2: Florence 32 + facial 22 = 54 invocações incluindo recovery;
  fluxo normal máximo 42. Prazo único de até 900s, incluindo fila e publicação.
- Sem rostos é resultado válido; falhas faciais preservam entregas Florence e
  ficam explícitas na cobertura. Limitação por número de rostos é visível.
- `/convert` oferece o novo perfil quando disponível; `/jobs/{id}` usa a
  operação/configuração durável para mostrar as camadas faciais também após F5.

Critérios adicionais qualificados pela implementação da 0012:

- [x] V2 recebe somente uma imagem e entrega as 18 famílias aplicáveis,
  sem romper o contrato, limite ou resultado do v1.
- [x] Operação específica e Full usam os mesmos adapters, modelos e regras
  de coordenadas/seleção; resultados equivalentes com configuração igual.
- [x] Prontidão e custos de todos os providers entram na admissão/dispatch;
  falha parcial, checkpoint, cancelamento, purge e F5 incluem as etapas faciais.
