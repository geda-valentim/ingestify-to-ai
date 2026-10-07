# Datalakes configuráveis por usuário

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

Verificado em 2026-10-06 contra API, workers e frontend de desenvolvimento.

O menu **Datalakes** permite cadastrar conexões AWS S3, MinIO, Google Cloud
Storage (GCP) e Azure Blob Storage. Cada solicitação de documento, transcrição
de áudio/vídeo ou captura ao vivo pode escolher conexão, bucket e pasta de
destino. No Azure, bucket significa container. É possível escolher buckets
existentes ou criar um bucket na etapa **Buckets**.

## Configuração pelo frontend

1. Abra `/datalakes`, clique em **Nova conexão** e escolha o provedor na etapa **Conexão**.
2. Informe as credenciais: access/secret key para S3 ou MinIO (session token
   opcional no S3), JSON de conta de serviço no GCP ou connection string no
   Azure. O MinIO exige endpoint; S3 aceita endpoint e região opcionais.
3. Clique em **Ver buckets**. Na etapa **Buckets**, veja a lista da conta,
   busque por nome e selecione os permitidos, ou permita todos os acessíveis.
   Quando não houver permissão de listagem, use **Verificar outro bucket**.
   A descoberta usa as credenciais em memória e não salva a conexão.
   **Criar bucket agora** cria o bucket na conta informada e o inclui na seleção.
   Marque **Usar como bucket padrão** para preencher o padrão automaticamente.
   S3/MinIO usam a região da conexão (ou `us-east-1`); GCP permite informar
   a localização (inicialmente `US`); Azure cria um container privado na conta.
   A criação exige permissão de verificar e criar buckets. Nomes já existentes
   são recusados sem alterar o bucket. Cancelar depois não apaga o bucket criado.
4. Em **Padrões**, escolha o bucket numa lista e informe a pasta sugerida.
   O bucket padrão deve pertencer à seleção permitida. Confira **Revisão** e
   clique em **Salvar conexão**. Cancelar qualquer etapa não altera a conexão.
5. Use **Testar conexão** para verificar acesso de leitura aos metadados do
   bucket. A entrega exige também permissão de criar/substituir objetos.
6. No dashboard ou na captura ao vivo, selecione **Destino dos resultados** e
   escolha o bucket numa lista que identifica o padrão. **Usar padrões da conexão**
   restaura bucket e pasta. A escolha da solicitação é salva junto com o job.
7. A aba **Datalake** do dashboard permite selecionar um arquivo já armazenado
   em um bucket. A origem e o destino podem usar conexões e buckets diferentes.

Credenciais nunca são devolvidas pela API nem persistidas pelo frontend.
Na edição, deixar os campos de credenciais vazios mantém as atuais. Para
rotacioná-las, informe todas as credenciais obrigatórias do provedor.
Conexões vinculadas a jobs podem ser desativadas; sua exclusão é bloqueada
enquanto existirem esses vínculos.

## API

Todas as operações exigem autenticação e respeitam o dono da conexão/job.

A [referência completa](../api-reference.md) documenta campos obrigatórios,
modelos, limites, tipos de conteúdo e respostas de cada operação.

| Operação | Endpoint |
| --- | --- |
| Listar/criar conexões | `GET/POST /datalakes` |
| Descobrir buckets sem salvar (ou verificar um bucket pelo nome) | `POST /datalakes/discover` |
| Criar bucket/container na conta, sem salvar a conexão | `POST /datalakes/buckets` |
| Calcular prévia sem acessar storage | `POST /datalakes/partition-preview` |
| Editar/excluir conexão | `PATCH/DELETE /datalakes/{id}` |
| Verificar acesso | `POST /datalakes/{id}/test` |
| Listar buckets | `GET /datalakes/{id}/buckets` |
| Listar arquivos | `GET /datalakes/{id}/objects?bucket=...&prefix=...` |
| Processar arquivo do bucket | `POST /datalakes/import` |
| Consultar entrega | `GET /jobs/{job_id}/datalake` |
| Repetir entrega | `POST /jobs/{job_id}/datalake/retry` |

Na importação, `conversion_options` segue `DocumentOptions` para documentos.
Áudio/vídeo aceita `audio_options` (`AudioConversionOptions`): operação,
decodificação por provider, timestamps, formato padrão e retenção. Os controles
são validados antes de baixar os bytes. Não envie controles de áudio para um
documento nem controles Docling para mídia; a API retorna 422. O front identifica
áudio/vídeo pelo caminho do arquivo e mostra os mesmos controles do upload local.

`POST /upload`, `/convert` e `/transcribe` aceitam os campos multipart
`datalake_connection_id`, `datalake_bucket` e `datalake_prefix`.
Criação de sessão ao vivo aceita `datalake: {connection_id, bucket, prefix}`
no JSON. `/datalakes/import` aceita esses mesmos dados em `datalake`, além
de `connection_id`, `bucket`, `key` para a origem e localização do projeto.

Exemplo de configuração MinIO (valores ilustrativos):

```json
{
  "name": "Datalake da equipe",
  "provider": "minio",
  "config": {
    "endpoint": "https://minio.example.com",
    "buckets": ["documentos", "transcripts"],
    "default_bucket": "transcripts",
    "default_prefix": "reunioes"
  },
  "credentials": {"access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}
}
```

## Resultados e recuperação

Resultados ficam em `{prefix}/{job_id}/` no bucket escolhido:
`result.json` (payload completo), `result.md`, `metadata.json` e, quando
presentes no resultado da transcrição, `transcript.txt`, `.srt`, `.vtt`, `.json`.
O armazenamento interno preserva o resultado para retry após expiração do
Redis. A entrega tem status próprio (`pending`, `exporting`, `completed`,
`failed`); falhas externas não alteram o job concluído nem repetem inferência.
Escritas substituem as mesmas chaves em cada tentativa. Até cinco tentativas
automáticas; a página do job oferece retry manual após corrigir a conexão.
O Beat reconcilia entregas sem mensagem no broker a cada minuto.

Documentos também entregam as exportações solicitadas em `document.<formato>`
(`document.md` para Markdown) e as imagens referenciadas em `assets/`.
As referências são relativas ao diretório de destino tanto nas exportações quanto
em `result.md` e `result.json`. Portanto, continuam válidas quando o job de origem
é excluído. O snapshot interno mantém as URLs privadas originais; o conteúdo
entregue é independente dessas URLs. Parâmetros e formatos em
[conversão de documentos](conversion.md).

Excluir um job remove seu snapshot interno, mas preserva seus arquivos no
bucket externo. A retenção externa é controlada pelo usuário/provedor.
Solicitações com destino explícito criam um novo job, mesmo quando o arquivo
já foi processado, para não ignorar a escolha daquele destino.

## Operação

`datalake_connections` e `job_datalake_exports` são criadas pelo `init_db`
no startup da API, sem alterar colunas de tabelas existentes. Atualize as
dependências e reinicie API, workers e Beat juntos. Builds normais incluem
`requirements-datalake.txt`; `Dockerfile.datalake-upgrade` permite acrescentar
os SDKs a uma imagem local existente sem reinstalar seus modelos/CUDA.

As credenciais usam Fernet com vínculo ao usuário e ao ID da conexão.
`DATALAKE_ENCRYPTION_KEY` permite uma chave estável dedicada, compartilhada
entre API e workers. Sem ela, a chave é derivada de `JWT_SECRET_KEY` com domínio
específico. Mantenha a chave e seu backup; trocar a chave ativa exige
reconfigurar as credenciais. Nenhum adapter utiliza credenciais ambientais
do servidor.

Os adapters usam o [cliente MinIO para S3](https://github.com/minio/minio-py/blob/master/docs/API.md),
o [SDK Google Cloud Storage](https://docs.cloud.google.com/storage/docs/uploading-objects-from-memory)
e o [SDK Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-python).

## Verificação

`backend/tests/test_datalakes.py` cobre os quatro provedores, isolamento por
usuário, criptografia, descoberta sem persistir rascunhos, bucket por solicitação,
importação, recuperação após expiração do Redis, limite de tentativas e retry
manual. Inclui criação com credenciais de rascunho ou da conexão existente,
região, nomes inválidos, conflitos, permissões e contratos dos quatro SDKs.
`frontend/tests/datalakes-browser.py` verificou configuração dos quatro
provedores no frontend, conversão e entrega reais no MinIO/S3 compatível,
importação de um bucket para outro, retry preservando o resultado e telas
desktop/mobile, incluindo criação real de buckets, seleção do padrão e
cancelamento sem remover o bucket criado. Também foi verificada entrega real dos sete artefatos de
uma transcrição sintética pela finalização comum e pelo Celery.
GCP e Azure foram verificados pelos contratos dos SDKs; não foram usadas
contas externas desses provedores. As contas, buckets e jobs de teste foram
removidos após a verificação.

## Particionamento configurável

Na etapa **Padrões**, escolha **Atual**, **Por data**, **Projeto + data** ou
**Personalizada**. A opção atual preserva `{prefix}/{job_id}/`. Os demais
presets produzem diretórios Hive `chave=valor` sob uma raiz de layout versionado:

```text
exports/layout-<versão>/project_id=<id>/year=2026/month=10/day=06/<job_id>/
```

Data usa a criação do job, convertida para o fuso IANA configurado. A granularidade
pode ser mês, dia ou hora. Na estratégia personalizada, adicione e reordene data,
ano, mês, dia, hora, ID de projeto, ID de pasta, origem e campos como `cliente`
ou `departamento`. Até oito campos e dez chaves expandidas, sem duplicatas.
Valores ausentes usam um substituto ou exigem preenchimento antes de enviar.
Valores são codificados reversivelmente; o caminho completo tem limite de
1.024 bytes. IDs de projetos novos são ilustrativos na prévia até a solicitação.

A conexão salva `config.partitioning` e `config.default_partition_values`.
Cada solicitação herda esses padrões; **Personalizar particionamento nesta
solicitação** permite alterar a estratégia. Valores personalizados podem ser
preenchidos para aquele job; **Usar padrões da conexão** restaura todas as escolhas.
Na API multipart, envie JSON em `datalake_partitioning` e
`datalake_partition_values`. Nos destinos JSON de import/live, use `partitioning`
e `partition_values`. Omitir a estratégia herda a conexão; `{ "mode": "none" }`
seleciona explicitamente o caminho atual.

`POST /datalakes/partition-preview` calcula a prévia autenticada sem acessar
storage. Aceita conexão existente ou estratégia de rascunho, valores, prefixo,
data e contexto ilustrativo. Usa a mesma resolução do job. Estratégia, valores,
contexto e caminhos ficam congelados em `job_datalake_partitions`. Editar a
conexão, mover o job ou executar retry preserva o destino e o conteúdo analítico.
Conexões e exports antigos continuam no caminho atual. A API do job devolve
`resolved_path`, `layout_id`, `partitions`, `dataset_path` e `schema_path`.
A migration é aditiva; `scripts/migrate_datalake_partitions.py` cria a tabela
idempotentemente sem alterar stamps legados do Alembic.

### Dataset JSONL e esquema

**Arquivos + dataset JSONL** acrescenta uma linha normalizada por job concluído:

```text
exports/datasets/layout-<versão>/<partições>/<job_id>.jsonl
exports/schemas/layout-<versão>.json
```

A raiz de datasets contém somente JSONL; legendas, Markdown e resultados completos
ficam na raiz de artefatos. O esquema v1 contém versão, ID do job, timestamp UTC,
IDs de projeto/pasta, origem, filename, texto, metadados JSON, payload completo JSON
e valores personalizados/partições JSON. `partition_values_json` preserva todos os
valores enviados ou herdados, inclusive chaves fora da estratégia. Valores resolvidos
das partições prevalecem, incluindo substitutos para campos ausentes.
Os três campos JSON são strings serializadas, permitindo
metadados variáveis sem alterar colunas. Colunas obtidas pelo caminho Hive são
omitidas da linha; o arquivo de esquema informa a ordem das partições, todas STRING.

Consulte cada raiz de layout separadamente, usando o esquema exportado.
Athena/BigQuery/Spark precisam da configuração de catálogo/tabela pelo consumidor;
a exportação não cria esses recursos. A especificação completa está em
[0008](../specs/0008-particionamento-configuravel-datalakes.md).

A verificação inicial de particionamento incluiu 31 testes dedicados, além das suites de
datalake, contratos da API, live e streaming de uploads: 311 testes passaram.
`frontend/tests/datalake-partitions-browser.py` verificou configuração personalizada,
ordem, fuso, bloqueio de erros, restauração de padrões, override, conversão PDF real,
entrega JSONL no MinIO e retry preservando o caminho após mudar o padrão. As telas
foram verificadas em desktop e celular, incluindo a prévia do destino live.
O agente de revisão não encontrou bloqueadores após as correções.

### Conversas de agentes agrupadas por cliente via API

Configure a estratégia por API na conexão (`config.partitioning`) ou na solicitação.
Para uma conta que atende vários clientes, use `tenant_id` e `client_id` como partições
obrigatórias, sem um cliente padrão. Envie `conversation_id`, `agent_id` e, se necessário,
`occurred_at` como contexto: essas chaves ficam no JSONL sem criar mais diretórios.
Use IDs estáveis do seu sistema; `client_id` é seu cliente final, não o usuário
autenticado do Ingestify. A propriedade da conexão/job continua controlando acesso;
uma dimensão de tenant não cria uma política de autorização adicional.

Exemplo de transcrição com a estratégia enviada por solicitação:

```bash
curl --fail-with-body 'https://dev.ingestify.ai/api/transcribe' \
  -H "Authorization: Bearer $INGESTIFY_TOKEN" \
  -F 'file=@conversation.mp3' \
  -F 'project=Atendimento' \
  -F 'datalake_connection_id=YOUR_CONNECTION_ID' \
  -F 'datalake_bucket=transcripts' \
  -F 'datalake_prefix=conversations' \
  -F 'datalake_partitioning={"mode":"custom","fields":[{"field":"custom","key":"tenant_id"},{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"}' \
  -F 'datalake_partition_values={"tenant_id":"tenant-1","client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent","occurred_at":"2026-10-06T14:30:00Z"}'
```

O dataset produz arquivos distintos para cada job:

```text
conversations/datasets/layout-<versão>/tenant_id=tenant-1/client_id=client-42/<job_id>.jsonl
```

Cada linha conserva o texto e `job_id`. Seu `partition_values_json`, após interpretar
a string JSON, contém:

```json
{
  "tenant_id": "tenant-1",
  "client_id": "client-42",
  "conversation_id": "chat-7",
  "agent_id": "support-agent",
  "occurred_at": "2026-10-06T14:30:00Z"
}
```

Uma consulta pode ler a partição daquele cliente e reunir suas conversas para
análise, mantendo a identificação de cada conversa. O Ingestify exporta registros
separados; o consumidor faz a consulta/agregação. Não concatena automaticamente
as conversas em um arquivo nem executa uma análise conjunta.

Para herdar a estratégia, salve-a em `config.partitioning` por `POST /datalakes`
ou `PATCH /datalakes/{id}` e omita `datalake_partitioning` nos próximos envios.
`PATCH` com `config` substitui a configuração completa: preserve endpoint, região,
buckets e demais opções já existentes. `config.default_partition_values` pode
guardar um tenant/agent padrão; os valores da solicitação prevalecem.
Editar a estratégia pelo wizard preserva atributos de contexto definidos pela API
que não eram partições. Remover uma dimensão pelo wizard limpa o padrão daquela
dimensão, mantendo os demais atributos.

Upload/conversão usam os mesmos campos multipart. Importação e criação de sessão
live recebem a estratégia e os valores dentro de `datalake`, usando `partitioning`
e `partition_values`. Consulte `POST /datalakes/partition-preview` antes do envio
e `GET /jobs/{job_id}/datalake` depois para verificar valores e caminhos congelados.

Se acrescentar data como partição, ela representa a criação do job, convertida
para o fuso escolhido; não a data histórica da conversa. Preserve a data do evento
em `occurred_at` para analisá-la. Reenviar `conversation_id` gera um novo job;
essa chave não oferece idempotência. Entregas já concluídas não são regravadas
automaticamente por esta correção; novas entregas e retries pendentes incluem
todos os valores do snapshot.

Seis testes adicionais verificam contexto sem partição, substitutos e três
pontos de entrada com duas conversas de um cliente e outra de um segundo cliente.
O teste de retry também verifica que alterações nos padrões não mudam esses IDs.
A extensão passou 134 testes: 37 de particionamento, 59 de datalakes e 38 do
contrato API/frontend. O frontend compilou com validação de tipos.
No dev, três PDFs de conversas passaram pela API, Celery e MinIO: duas conversas
compartilharam a partição de um cliente e a terceira ficou na partição de outro.
Os três registros mantiveram `conversation_id`, `agent_id` e `occurred_at`, sem
criar diretórios para esses atributos. Os exemplos públicos foram conferidos em
PT/EN, desktop/mobile. A conta e os recursos de teste foram removidos.
Um segundo teste real criou padrões pela API e editou fuso/granularidade no
wizard sem perder `conversation_id`/`agent_id`. Remover a dimensão `client_id`
limpou apenas o valor dessa dimensão e conservou o contexto adicional.
