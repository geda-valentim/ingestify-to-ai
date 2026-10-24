# Idiomas da API (inglês por padrão, português sob pedido)

## O que faz

O texto legível das respostas (`message`, `next_steps` só trazem identificadores) sai em
**inglês por padrão** e em **português (pt-BR)** quando o cliente pede. O `code` de cada
erro é estável e não depende do idioma: clientes devem ramificar por `code`, nunca por
`message`.

## Como usar

O idioma vem do header padrão `Accept-Language`:

```bash
# inglês (padrão, também sem header)
curl -s -F file=@vazio.pdf -F project=P -H "X-API-Key: ..." .../upload
# {"detail":{"code":"FILE_EMPTY","message":"The uploaded file is empty."}}

# português
curl -s -F file=@vazio.pdf -F project=P -H "X-API-Key: ..." -H "Accept-Language: pt-BR" .../upload
# {"detail":{"code":"FILE_EMPTY","message":"Arquivo enviado está vazio"}}
```

Negociação (RFC 9110, simplificada):

- tags `en*` e `pt*` (`pt`, `pt-BR`, `pt-PT`) são as únicas suportadas; vence a de maior
  `q` (empate: a que vier primeiro); `q=0` exclui a tag;
- `*`, idiomas desconhecidos, header ausente ou malformado resultam em inglês;
- não há `?lang=` (pode vir depois, sem quebrar nada).

Toda resposta traz `Content-Language: en` ou `pt-BR` e `Vary: Accept-Language` (caches e
proxies guardam uma cópia por idioma), inclusive o 500 de produção. A interface web pede
`Accept-Language: en`, exceto as telas em português (`/live`, as telas de imagem e o resultado de jobs de imagem, as opções
de imagem do formulário de upload e as telas de datalake), que pedem `pt-BR` nas suas chamadas.

## O que muda de idioma

Todo texto de erro e de orientação da API: recusas de `/upload`, `/convert` e `/transcribe`,
localização de upload (projeto/pasta), tags, sessões ao vivo, `GET /search`, autenticação e
API keys, datalake e imagens (inclusive o envelope `error_code`/`message` de `/images/*`),
administração (`/admin/*`, engines, roteamento), controle de engines, perfis de execução,
acesso e IAM, e os 404 de job/projeto/pasta/API key. O `code` é o mesmo em qualquer idioma,
assim como `next_steps` (identificadores). Nas recusas que embrulham uma exceção de domínio
(engines, roteamento, IAM) o texto original, sempre em inglês, vai em `technical`.

O `message` de engine-control que volta em corpos de `GET` (`setup`, ações de
`capabilities`) segue o idioma da requisição, como os erros.

Idioma por tela da interface de administração: as telas de computação (`/admin/engines`,
`/admin/engines/[id]`, `/admin/gpus`, `/admin/routing`, `/admin/status`, via `adminGet`) são
em inglês e usam o padrão; as telas de controle de engines, perfis de execução, acesso e IAM
(via `controlRequest`) são em português e pedem `pt-BR`. Os rótulos de `next_steps` ficam em
português nas duas.

Os 404 que não revelam o que existe continuam **texto** (não objeto), agora no idioma
pedido (em `/images/*` só o de `POST /images/{id}/cancel`; o de conexão de datalake dentro de
`/images/*` é `DATALAKE_NOT_FOUND` no envelope `error_code`). "Não existe" e "não é seu" respondem o mesmo corpo, em cada idioma.

## O que NÃO é traduzido

- a mensagem de validação do FastAPI/Pydantic (422 com `detail` em lista) segue em inglês;
- mensagens de erro gravadas em jobs pelos workers (`error`, `error_message`) saem em
  inglês; linhas já gravadas ficam como estão;
- descrições de figuras (Florence-2 só gera inglês); "figuras em PT-BR" está adiado;
- textos do OpenAPI/Swagger (esquema estático em português).

## Mudança de comportamento

Clientes que não enviavam `Accept-Language` recebiam português e passam a receber inglês.
Quem precisa do texto em português envia `Accept-Language: pt-BR`. Quem casava texto de
`detail` deve passar a casar `detail.code`.

## Limites e lacunas conhecidas

- Todo código do catálogo tem texto em inglês e em português
  (`backend/tests/test_error_catalog.py` falha se faltar um).
- O idioma é decidido na requisição; tarefas em segundo plano e Celery usam inglês.
