# 0012 — Detecção facial e análise de expressões

| | |
|---|---|
| **Status** | Implementada; qualificada em ambiente isolado; ativação opt-in |
| **Autor** | Codex, a pedido de Geda Valentim |
| **Criada em** | 2026-10-06 |
| **Atualizada em** | 2026-10-06 |
| **Relacionadas** | [0003](0003-motores-de-execucao-roteamento-e-orcamento.md), [0011](0011-full-analysis.md) |
| **Substituída por** | — |

## 1. Problema

O usuário precisa detectar rostos e analisar suas expressões em imagens enviadas
pelo `/convert` ou pela API. O catálogo Florence-2 atual não oferece landmarks,
blendshapes ou um classificador facial dedicado. Descrever uma pessoa numa
caption não entrega esses resultados estruturados.

Essa análise precisa funcionar separadamente e também integrar o **Full Analysis**,
com uma única imagem, um único job e resultados que continuem disponíveis após F5.

## 2. Objetivo

Oferecer **Rostos e expressões** como operação específica e acrescentar suas três
famílias ao Full Analysis: detecção facial, geometria/movimentos faciais e
classificação de expressão, usando modelos executados no worker.

As categorias e os scores descrevem estimativas de expressão visível. Não são
medições do estado emocional interno de uma pessoa. O produto deve usar
“expressão estimada” e “movimentos faciais” nos relatórios e na interface.

### Fora de escopo

- Reconhecimento de identidade, comparação de pessoas, embeddings faciais e cadastro biométrico.
- Inferências de idade, gênero, etnia, personalidade, saúde ou diagnóstico.
- Vídeo, câmera ao vivo, tracking entre frames e associação com falantes.
- API paga, treino de modelo ou classificação de expressão via caption Florence.
- Salvar/exportar automaticamente arquivos separados com recortes de rostos.

## 3. Critérios de aceitação

- [x] `/convert` aceita upload de imagem para a operação específica, incluindo
  detecção simples ou detecção com expressões, conforme as capacidades do worker.
- [x] JSON e multipart aceitam os mesmos parâmetros; opções desconhecidas ou
  incompatíveis são rejeitadas antes de criar o job.
- [x] Cada rosto selecionado tem ID local ao job, caixa, confiança de detecção,
  keypoints e resultados/estados independentes de movimentos e classificação.
- [x] Um resultado vazio de detecção é válido; falha de modelo não vira “nenhum rosto”.
- [x] Limite de rostos e omissões ficam visíveis, sem afirmar análise de todos
  os rostos quando somente um subconjunto foi selecionado.
- [x] Full `image-full-v2` inclui as 15 famílias Florence e as três faciais,
  com cobertura por família e por rosto, preservando o contrato `image-full-v1`.
- [x] O job exibe opções efetivamente aplicadas, modelos, versões e resultados
  persistidos; F5, Redis expirado e redelivery conservam esses dados.
- [x] Falha, timeout ou cancelamento preservam etapas duráveis e não recebem
  selo de cobertura integral; a exclusão remove seus artefatos derivados.
- [x] A mesma imagem canônica, configuração e modelos produzem resultados
  faciais equivalentes na operação específica e no Full, dentro da tolerância publicada.
- [x] Código e cada artefato de modelo têm licença, origem, revisão e checksum
  registrados; a capacidade só é anunciada como pronta após qualificação real.

## 4. Solução proposta

### 4.1 Modelos e significado dos resultados

| Etapa | Implementação proposta | Entrega |
|---|---|---|
| `face_detection` | MediaPipe Face Detector, modo `IMAGE` | Caixas, confiança de detecção e seis keypoints |
| `face_movements` | MediaPipe Face Landmarker, modo `IMAGE`, blendshapes habilitados | 478 landmarks e 52 coeficientes de movimentos faciais por rosto |
| `face_expression_classification` | EmotiEffLib com checkpoint ONNX qualificado | Scores por classe de expressão e classificação conclusiva/inconclusiva |

São adapters próprios; não acrescentar tokens faciais ao `VisionTask` do Florence.
O Landmarker contém modelos internos adicionais: uma invocação do adapter não
equivale a uma única passagem de rede neural. Blendshapes são coeficientes de
movimento; não convertê-los em probabilidades de emoção nem em unidades FACS.

Fontes técnicas: [Face Detector](https://developers.google.com/edge/mediapipe/solutions/vision/face_detector/python),
[Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python)
e [EmotiEffLib](https://github.com/sb-ai-lab/EmotiEffLib).
As classes do classificador dependem do checkpoint: preservar nomes, ordem e
quantidade nativos no manifesto; não fixar sete ou oito classes sem escolhê-lo.

Os códigos de [MediaPipe](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)
e [EmotiEffLib](https://github.com/sb-ai-lab/EmotiEffLib/blob/main/LICENSE) têm licença
Apache-2.0. Isso não qualifica automaticamente a licença de todos os pesos.
Antes da ativação, registrar para **cada** artefato: URL/model card, licença dos
pesos, permissão de uso pretendido, revisão, SHA-256, versões do runtime,
pré-processamento e labels. Checkpoint sem licença verificada bloqueia a etapa.

### 4.2 Contrato da operação específica

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/images/faces/capabilities` | JWT ou API key | Etapas disponíveis, parâmetros, limites e modelos qualificados |
| POST | `/images/faces` | JWT ou API key | Imagem base64 e opções tipadas |
| POST | `/images/faces/upload` | JWT ou API key | Upload multipart e as mesmas opções |
| GET | `/jobs/{job_id}` | Dono do job | Configuração persistida e progresso |
| GET | `/jobs/{job_id}/result` | Dono do job | Resultado facial ou Full, conforme operação persistida |
| POST | `/images/{job_id}/cancel` | Dono do job | Estender o cancelamento composto para jobs faciais |

Os POST de criação exigem `Idempotency-Key`. Usar o contrato da 0011:
mesmo dono/operação/payload devolve o mesmo job; payload diferente retorna `409`;
job excluído retorna `410` durante a retenção de 24h da chave. Nenhuma mudança
nos requisitos das operações individuais de imagem já existentes.

Exemplo de request JSON; o conteúdo de `image_base64` é abreviado:

```json
{
  "image_base64": "<base64 da imagem>",
  "filename": "foto.jpg",
  "project": "default",
  "wait": false,
  "face_options": {
    "mode": "expressions",
    "max_faces": 5,
    "min_detection_confidence": 0.5,
    "min_suppression_threshold": 0.3,
    "min_face_presence_confidence": 0.5,
    "min_expression_score": 0.5,
    "deadline_seconds": 300
  }
}
```

Multipart aceita `file`, `face_options` como JSON, `wait`, `tags`, localização
de projeto/pasta e `datalake` conforme os contratos atuais. Sem campos soltos
de parâmetros de modelo. Base64 e upload compartilham a mesma validação de MIME,
tamanho e decodificação, com limites publicados no catálogo.

| Opção em `face_options` | Padrão | Validação e aplicação |
|---|---|---|
| `mode` | `expressions` | `detection` ou `expressions`; a segunda exige as três etapas |
| `max_faces` | 5 | Inteiro 1–10 na operação específica; 1–5 no Full v2 |
| `min_detection_confidence` | 0.5 | Número finito 0–1; filtro do Face Detector |
| `min_suppression_threshold` | 0.3 | Número finito 0–1; supressão do Face Detector |
| `min_face_presence_confidence` | 0.5 | Número finito 0–1; Landmarker, somente `expressions` |
| `min_expression_score` | 0.5 | Número finito 0–1; somente `expressions`; abaixo do limiar, classificação inconclusiva |
| `deadline_seconds` | 300 | Inteiro 1–300; prazo total da operação específica |

`max_faces` é um limite da aplicação; não é uma opção nativa do Face Detector.
O Landmarker usa `num_faces=1` por recorte e confiança interna de detecção 0.5,
ambas registradas no manifesto/configuração efetiva. Não expor parâmetros de
tracking no MVP de imagens, nem URL de checkpoint, paths ou código de modelo.
Em `detection`, parâmetros exclusivos de expressão explicitamente enviados
retornam `422`; defaults exclusivos não são aplicados. Schemas usam `extra=forbid`.

Resposta `202`: `job_id`, `status=pending`, `poll_url` e `result_url`, como no
Full atual. `wait=true` retorna o resultado terminal ou `504` com o ID e URLs;
o timeout HTTP não cancela o job. Erros: `401` autenticação; `403` autorização
de operação/engine; `404` job de outro dono/inexistente; `409/410` idempotência;
`413` tamanho; `422` imagem/opções inválidas; `503` ausência de executor com
todas as etapas solicitadas prontas; `504` espera HTTP excedida.

### 4.3 Fluxo, rostos e coordenadas

```text
API → validação/capacidades → job + snapshot SQL + outbox → Celery/engine
    → imagem canônica MinIO → Face Detector → seleção persistida
    → Landmarker e classificador por rosto → checkpoints SQL/MinIO
    → relatório durável → /jobs/{id} e /jobs/{id}/result
```

1. Decodificar uma vez, normalizar EXIF e usar a política atual de primeiro
   frame para formatos multiframe. No Full, compartilhar a imagem canônica com Florence.
2. Filtrar detecções válidas, ordenar por confiança decrescente, área decrescente
   e coordenadas como desempate; selecionar até `max_faces`.
3. Persistir detecção, seleção, IDs `face-001…`, contagens e transformações de
   recorte antes das etapas por rosto. IDs só valem dentro do job; não são identidade.
4. Em `expressions`, processar cada rosto selecionado. Padding, alinhamento,
   resize e normalização seguem o manifesto fixado de cada modelo. Recortes
   existem em memória; seus dados geométricos ficam no checkpoint.
5. Remapear keypoints/landmarks para a imagem canônica. Verificar a associação
   geométrica ao rosto selecionado; associação ambígua ou ausência de malha
   gera motivo explícito, sem atribuir a expressão de outro rosto. O classificador
   só depende da malha quando seu manifesto exige esse alinhamento.

Caixas: `[x1,y1,x2,y2]`, pixels da imagem canônica e versão normalizada em
0–1. Registrar tamanho e transformação; limitar caixas aos limites da imagem.
Landmarks mantêm índice e coordenadas nativas/remapeadas, com unidade explícita;
`z` é relativo ao modelo, não profundidade métrica. Não inventar confiança
individual de landmark quando o provider não a retorna.

`detected_count` conta as detecções válidas retornadas pelo detector, não todas
as pessoas efetivamente presentes. Incluir `selected_count`, `omitted_count`,
`selection_limited` e `omission_reason=max_faces`. O limite define o alcance
solicitado; completar o subconjunto não autoriza afirmar cobertura de todos os rostos.

### 4.4 Resultado tipado e estados

Resultado específico: `operation=face_analysis`, `schema_version=face-result-v1`,
`profile=image-faces-v1`; manter campos comuns de job/imagem e acrescentar:

| Campo | Conteúdo |
|---|---|
| `request` | Snapshot completo de parâmetros efetivos, inclusive defaults e prazo |
| `models` | Modelo/revisão/checksum/runtime/provider por etapa |
| `detection` | Estado, contagens, limitação e motivo; separado das expressões |
| `faces[]` | ID, caixa, confiança de detecção, keypoints, `movements` e `expression` |
| `steps[]` | Etapa, face ID quando aplicável, inputs, estado, motivo, tentativas e duração |
| `coverage` | Famílias solicitadas/concluídas e instâncias por rosto |
| `analysis_status` | `completed`, `partial`, `failed` ou `cancelled` |
| `calls_started` | Total e subtotais por adapter, incluindo tentativas interrompidas |

`movements` conserva os landmarks e todos os blendshapes com seus nomes nativos.
`expression` conserva vetor completo de scores, ordem de labels, melhor classe,
`score_kind`, `calibrated=false` e limiar aplicado. Se o checkpoint retorna
logits, o adapter usa softmax documentado no manifesto; não tratar os scores
como probabilidades calibradas. Abaixo do limiar, `decision=inconclusive` e
`label=null`, preservando os scores. Isso é resultado válido, não falha técnica.

Etapas mantêm `pending/running/succeeded/failed/skipped/not_applicable` e
`reason_code`. Em detecção simples, expressões ficam fora da cobertura solicitada,
com `not_requested`. Se a detecção concluiu sem rostos, retornar `faces=[]` e
etapas dependentes `not_applicable/no_faces`: a análise pode ser `completed`.
Se a detecção falhou, dependências recebem `skipped/dependency_failed`.

Expressão inconclusiva é diferente de falha/ausência de malha. Em execução com
falhas, retornar `partial` quando há resultados úteis; sem etapa útil, `failed`.
No Full, preservar as entregas Florence mesmo se uma etapa facial falhar.
`completed` exige todas as etapas aplicáveis solicitadas concluídas e publicação
durável; cancelamento conserva sua semântica atual e os checkpoints já concluídos.

### 4.5 Integração no Full Analysis

Adicionar `full_options.profile` com default **`image-full-v1`** para chamadas
antigas. O novo perfil **`image-full-v2`** executa as 15 famílias da 0011 e as
três famílias faciais. Suas opções incluem `full_options.faces`, com os mesmos
parâmetros faciais, `mode=expressions` obrigatório e `max_faces≤5`. Não permitir
desativar silenciosamente uma das três etapas nesse perfil.

```json
{
  "image_base64": "<base64 da imagem>",
  "filename": "foto.jpg",
  "project": "default",
  "mode": "full",
  "wait": false,
  "full_options": {
    "profile": "image-full-v2",
    "deadline_seconds": 900,
    "faces": {
      "mode": "expressions",
      "max_faces": 5,
      "min_detection_confidence": 0.5,
      "min_suppression_threshold": 0.3,
      "min_face_presence_confidence": 0.5,
      "min_expression_score": 0.5
    }
  }
}
```

O prazo do Full é único: `deadline_seconds` dentro de `faces` retorna `422`.
`faces` com perfil v1 também retorna `422`. Omissão de `faces` no v2 aplica os
defaults, sem exigir campos extras além da imagem e da seleção do perfil.

Resultado v2: `schema_version=image-full-result-v2`, `profile=image-full-v2`,
18 famílias na cobertura, bloco `faces` com o contrato facial acima e `models`
com todos os providers. `results` passa a ser uma união discriminada por `kind`:
`florence` mantém `task: VisionTask`; `face` usa `operation` com os três literais
faciais e `face_id` quando aplicável. Não reutilizar `VisionModelInfo` Florence
como se representasse todos os modelos. O resultado v1 permanece inalterado.

Catálogo `/images/capabilities` ganha `full_profiles` tipado com limites,
schemas de opções e requisitos de cada perfil. Conservar `full_profile` e
`full_limits` existentes para v1. Validar disponibilidade de todas as etapas
do perfil na admissão e na escolha do executor; nenhum fallback silencioso
para v1. Indisponibilidade surgida após admissão é registrada por etapa.

### 4.6 Execução, recuperação e limites

Reutilizar o orquestrador durável da 0011. Registrar os adapters faciais no
worker e carregar MediaPipe/ONNX somente ali; `shared/` conserva schemas,
catálogo e planejamento sem imports de runtime/API. Primeira implementação
qualifica execução facial CPU no mesmo executor do lote; não anunciar suporte
Modal/GPU para esses adapters sem validá-los nesse ambiente.

No Full v2, executar o ramo facial e depois o planner Florence existente;
falhas faciais não interrompem as tarefas Florence enquanto houver prazo.
Considerar prontidão, memória e orçamento de **todos** os modelos no dispatch.
Manter medição por etapa/provider no ledger: invocações de adapters diferentes
não têm o mesmo custo. Sem reserva/admissão de engine, não iniciar inferência.

| Perfil | Limites de invocações de adapters, incluindo recovery |
|---|---|
| `image-full-v1` | Florence 32, conforme 0011 |
| `image-full-v2` | Florence 32 + facial 22 = total 54; até cinco rostos |
| `image-faces-v1` | Facial `2 × (1 + 2 × max_faces)`; até 42 com dez rostos em `expressions` |

No v2, fluxo facial normal: uma detecção + cinco Landmarker + cinco classificações
= 11 invocações. Florence normal faz até 31; total normal máximo 42. O orçamento
facial 22 permite no máximo duas tentativas por etapa, inclusive tentativa
interrompida de resultado incerto. Em `detection`, são até duas invocações.
Não aumentar o `MAX_CALLS=32` global e alterar v1: os limites devem depender do
perfil e incluir subtetos por ramo, sem Florence consumir a reserva facial.

Incrementar contador antes de cada inferência; reusar checkpoints concluídos,
sem refazer detecção/seleção publicada. Fila, download/carregamento, inferência
e persistência consomem o prazo total (300s específico, até 900s Full).
Checar cancelamento/fence/prazo antes de cada etapa e publicação. Qualificar
hard timeout/watchdog também para chamadas nativas MediaPipe/ONNX que não
respondam ao soft timeout; writer tardio não pode substituir resultado terminal.

### 4.7 Persistência, configuração e retenção

Reutilizar `ImageAnalysisRun`, `ImageAnalysisStep` e `ImageAnalysisSubmission`,
o snapshot de configuração do job, outbox, lease/fence e objetos imutáveis da
0011. Persistir perfil, opções faciais efetivas, manifesto dos modelos,
seleção/transformações, famílias esperadas e subtotais de chamadas. Não depender
de um enum Florence para recuperar etapas faciais.

Planejar migração aditiva para guardar `profile` e `calls_by_provider` no run,
e `step_kind`/`provider` nas etapas; backfill dos registros existentes com
`image-full-v1`/`florence`, sem reescrever artefatos publicados. Detalhes por
rosto/transformações ficam nos inputs/outputs JSON dos checkpoints. Downgrade
somente após retirar jobs v2/faciais ativos e preservar/exportar seus dados.

Imagem fonte única por job e objetos sob `images/{job_id}/` para checkpoints
e relatórios. SQL decide o objeto vencedor por checksum/fence. Redis usa o
cache existente, com o mesmo TTL, sem nova fonte de verdade: reconstruir
job/resultado/cobertura a partir de SQL/MinIO. Datalake mantém o snapshot do
destino existente e exporta o resultado tipado, inclusive status parcial.

Autorizar leitura, cancelamento e exclusão pelo dono no SQL antes do cache.
Aplicar retenção/purge do job à imagem, dados faciais e relatório; não logar
base64/recortes/landmarks completos. Excluir durante execução invalida a lease
e impede criação tardia de artefatos sobreviventes.

### 4.8 Frontend e documentação

- `/convert`: operação **Rostos e expressões**, com seletor de detecção simples
  ou expressões, limites e thresholds permitidos pelo catálogo. Upload usa os
  endpoints específicos e mantém a chave idempotente durante retries.
- **Full Analysis**: oferecer v2 com rostos/expressões como padrão para novas
  submissões quando qualificado; manter seleção explícita do v1. Se v2 estiver
  indisponível, explicar o motivo e permitir escolher v1, sem troca automática.
- `/jobs/{id}`: renderizar pela operação/perfil/configuração persistidos,
  inclusive após F5. Mostrar progresso por família/rosto, contagens, omissões,
  falhas parciais e opções aplicadas. Não reconstruir opções dos defaults atuais.
- Sobre a imagem: camadas de caixas/keypoints/landmarks, seleção de rosto e
  painel com blendshapes e scores. Usar controles separados para movimentos e
  classificação; preservar labels nativos no JSON e traduzir somente a apresentação.
- Inconclusivo, sem rosto e falha técnica têm mensagens distintas. Texto de
  apoio: “Estimativa de expressão visível; não determina o estado emocional”.
- Exportar JSON tipado e Markdown derivado dos dados persistidos. Atualizar
  OpenAPI/referência gerada, guias de visão PT/EN e exemplos específicos/Full.

## 5. Alternativas consideradas

| Alternativa | Por que não foi escolhida |
|---|---|
| Pedir emoções numa caption Florence | Não fornece geometria/scoring facial especializado nem contrato por rosto |
| Somente Face Landmarker | Atende movimentos; não entrega o classificador proposto nem confiança do Face Detector |
| Somente classificador EmotiEffLib | Não cobre detecção, landmarks e movimentos solicitados |
| Serviço externo pago | Acrescenta dependência e envio externo de imagens; execução local atende esta proposta |
| Acrescentar etapas ao resultado Full v1 | Muda cobertura, custos e tipos de um contrato já qualificado |

## 6. Impactos

- **Compatibilidade:** rotas específicas e Full v2 são aditivos; v1 conserva
  defaults, schema, 15 famílias e teto 32. Clientes precisam escolher v2 para receber faces.
- **Performance:** novos modelos e até 11 invocações faciais normais no Full;
  medir CPU/RAM, cold start, latência p50/p95 e tamanho dos resultados antes de
  habilitar. Não assumir tempo real ou aceleração CUDA do MediaPipe Python.
- **Segurança:** mesmas autenticação/autorização de imagens; artefatos faciais
  compartilham retenção do job. Nenhuma função de identidade ou inferência sensível.
- **Operação:** propor `FACE_ANALYSIS_ENABLED=false` até a qualificação,
  dependências fixadas e manifestos administrados. Capabilities distingue
  desabilitado, dependência ausente, pesos ausentes, licença não qualificada e pronto.
- **Custo:** sem API de inferência paga no desenho inicial; há custo de CPU,
  memória, armazenamento e infraestrutura. Ledger mede cada provider separadamente.

## 7. Plano de testes

- **Unitários:** schemas/extra forbid/modos, limites distintos, seleção
  determinística, mapeamento de coordenadas e EXIF, IDs, contagens/omissões,
  thresholds, labels/scores, cobertura 15/18 e subtetos 32/22/54.
- **API:** paridade JSON/upload, idempotência, permissões/donos, cancelamento,
  catálogo real, admissão indisponível, campos incompatíveis, compatibilidade
  v1 e serialização discriminada dos resultados novos.
- **Integração:** providers controlados, checkpoint de seleção, retries/crash,
  Redis expirado, MinIO/SQL indisponível, fence perdido, writer tardio, purge,
  deadline desde fila, chamada nativa travada e ledger com medição ausente explícita.
- **Modelos reais:** container Python do projeto, CPU, checkpoints fixados;
  fixtures licenciadas de zero/um/vários rostos, rostos pequenos/ocluídos,
  rotação EXIF e mais rostos que o limite. Verificar geometria, formato,
  associação e igualdade específico/Full com tolerâncias registradas, sem
  usar “emoção verdadeira” como ground truth.
- **Frontend automatizado:** desktop/celular, upload, configuração, camadas,
  seleção de rosto, inconclusivo, partial, limite visível, downloads e F5 com
  defaults do servidor alterados depois da criação do job.
- **Documentação:** validar exemplos contra schemas/OpenAPI e links; comprovar
  origem/licença/checksum dos modelos usados na qualificação.

## 8. Plano de implementação

- [x] PR1 — Qualificar artefatos/licenças e runtime CPU; adapters e manifesto;
  catálogo de prontidão desabilitado por padrão.
- [x] PR2 — Schemas, rotas específicas, migração aditiva e orquestração facial
  com checkpoints, cancelamento, limites e accounting.
- [x] PR3 — Full v2 com união de etapas, 18 famílias, dispatch compatível e
  preservação dos testes/contratos v1.
- [x] PR4 — `/convert`, visualização por rosto, configuração durável no job,
  guias/OpenAPI e qualificação real antes de habilitar no ambiente.

## 9. Questões em aberto

- [x] Operação separada ou somente Full? → **Decisão (2026-10-06):** oferecer
  ambas; o usuário pediu operação específica e inclusão no Full Analysis.
- [x] O que significa expressão? → **Decisão:** movimentos observáveis e
  classes estimadas, com contratos separados e sem afirmar estado emocional interno.
- [x] Como preservar o Full existente? → **Decisão:** perfil/schema v2
  explícitos; omissão do perfil conserva v1 para clientes antigos.
- [x] Bundle fixado: BlazeFace short-range float16/1, Face Landmarker float16/1
  e EmotiEffLib `enet_b0_8_best_afew` na revisão
  `520a051c64cd191521e5934655314e769a319684`. SHA-256, licenças e
  pré-processamento estão no [manifesto](../../backend/shared/face_models.json).
- [x] Tolerância específico/Full: caixas idênticas e diferença absoluta nos
  scores de expressão ≤ `1e-5`, com opções/modelos iguais.

## 10. Implementação e qualificação (2026-10-06)

O usuário aprovou implementação e merge. A mudança acrescenta a operação
específica, Full v2 e as dependências necessárias do Full v1 à versão atual de
`main`; não inclui as demais mudanças acumuladas do checkout original.

- **Runtime real:** Python 3.13.16, MediaPipe 1.1.0 e ONNX Runtime 1.30.0;
  adapters faciais CPU. `libegl1`/`libgles2` incluídas na imagem do worker.
- **Artefatos:** URLs imutáveis/revisão, SHA-256 e origem de licença registrados
  no manifesto. Model cards de detector, Face Mesh V2 e Blendshape V2 declaram
  Apache-2.0. O ONNX é distribuído na revisão do repositório EmotiEffLib sob
  a licença Apache-2.0 da raiz; não acompanha licença distinta dos pesos.
  Essa base de atribuição está explícita no manifesto.
- **Fixture:** imagem NASA distribuída como `astronaut.png`
  pelo scikit-image v0.24.0, fornecida externamente à qualificação.
  Nenhuma imagem pessoal, peso ou resultado de usuário entra no Git.
- **Inferência:** operação específica concluiu 3/3 famílias, 478 landmarks,
  52 blendshapes e oito classes. Full v2 concluiu 18/18 famílias, 34 chamadas
  (31 Florence + 2 MediaPipe + 1 EmotiEffLib), em 27,482s no executor de teste
  com Florence CUDA. Esse tempo é uma medição da fixture, não um SLA.
- **Casos nativos CPU:** imagem branca sem detecções; EXIF com coordenadas
  canônicas (diferença de caixas ≤3px após JPEG); seis detecções em montagem,
  duas analisadas e quatro omitidas. Pico RSS do processo de qualificação:
  318,3MiB; chamadas faciais medidas entre 0,007s e 0,156s nessa execução.
  Valores não representam consumo completo do worker Florence.
- **Recuperação:** teste prefork isolado de inferência facial que ignora soft
  timeout, com ≥2,3s em fila: hard kill em 6,7s para prazo total de 6s
  (arredondamento do timer); watchdog publica diagnóstico durável sem reexecutar.
- **Regressão:** 341 testes passando, abrangendo faces/Full/visão, entrega
  datalake, engines, admissão de transcrição, live, resultados e migrações.
- **Interface:** TypeScript e build de produção aprovados. Oito cenários
  Playwright em desktop (1440px) e celular (390px): upload, chave estável em
  retry, mudança de chave com opções, limite/omissões, seleção/camadas,
  expressão inconclusiva, falha parcial, vazio, exports, prontidão e F5.
  F5 conserva configuração mesmo quando defaults do catálogo mudam.

Reproduzir com `backend/tests/face_analysis_real_probe.py`,
`backend/tests/face_analysis_native_edges.py`,
`backend/tests/image_full_deadline_probe.py --faces` e
`frontend/tests/faces-browser.py`; consulte as instruções dos arquivos.

Ativação no ambiente exige migrações, imagem do worker com dependências,
`make faces-download` e `FACE_ANALYSIS_ENABLED=true` na API e no worker.
A flag permanece `false` por padrão; esta entrega não altera a configuração
nem os dados do ambiente em execução.
