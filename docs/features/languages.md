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
`Accept-Language: en`, exceto as telas em português (`/live`, as opções de imagem do
formulário de upload e o resultado de jobs de imagem), que pedem `pt-BR` nas suas chamadas.

## O que muda de idioma

Partes 1 e 2 (API 1.9.0). A parte 2 acrescenta as rotas de job restantes (resultado, páginas,
assets, retry, exclusão, listagem), autenticação (cadastro, login, sessão, 401, usuário
inativo), os 429 (`Retry-After` continua) e a criação de API keys; também os textos dos
corpos 200 (`message` de enfileirado, arquivo já processado, notas de `purge_source`). O
401 mantém `WWW-Authenticate: Bearer`.

Parte 1 (API 1.8.0): recusas de `/upload`, `/convert` e `/transcribe`, localização de
upload (projeto/pasta), tags, sessões ao vivo (503 e `GET .../availability`), `GET /search`
(503), `callback_url` inválido, erros de nome de projeto/pasta (inclusive o 422 de
`POST /api-keys`), limites de projeto/pasta e tags nas rotas `/images/*` (no envelope
`error_code`/`message`) e os 404 de job/projeto/pasta/API key. Datalake, imagens, admin, engines e IAM migram nas próximas partes e, até lá,
continuam em português; o `code` é o mesmo em qualquer idioma.

Os 404 que não revelam o que existe continuam **texto** (não objeto), agora no idioma
pedido. "Não existe" e "não é seu" respondem o mesmo corpo, em cada idioma.

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

- Alguns textos de engines/IAM/admin ainda não têm versão em inglês e respondem em
  português mesmo com `Accept-Language: en` (lista `PENDING_EN` em
  `backend/tests/test_error_catalog.py`; esvaziada na última parte).
- O idioma é decidido na requisição; tarefas em segundo plano e Celery usam inglês.
