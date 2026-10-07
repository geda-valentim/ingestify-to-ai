# Projetos: manutenção, estatísticas e movimentação

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

Verificado no código em **2026-10-05**. Página do produto: `/projects`, acessível
pelo menu **Projects**. Cada usuário administra seus próprios projetos e pastas.

## Interface

- **New project** cria um projeto antes de enviar arquivos. Um nome equivalente
  reutiliza o projeto existente, pelas regras compartilhadas de normalização.
- Escolha um projeto para consultar jobs concluídos, ativos, falhos e cancelados,
  total de jobs, volume original dos arquivos, última atividade e API keys vinculadas.
- **Edit project** altera a descrição e corrige caixa, acentos ou espaços do nome.
  A identidade normalizada permanece estável para os clientes automáticos.
- **Archive / Restore** suspende/retoma novos uploads para o projeto. Os resultados
  anteriores continuam disponíveis; keys devem ser desvinculadas antes de arquivar.
- **New folder** cria uma pasta dentro do projeto. Pastas têm um único nível;
  `Edit` permite correção cosmética. Excluir pasta devolve os jobs à raiz sem
  excluir arquivos, resultados ou tags.
- **Delete project** exige projeto vazio e sem keys vinculadas. Mova os jobs
  primeiro; a API responde `409` se ainda houver dependências.
- Em **My Jobs**, selecione jobs na página e use **Move selected**. Também há ação
  `Move` por linha e cartão **Location → Move** no detalhe do job. A troca de
  projeto limpa a pasta escolhida; **No folder** envia para a raiz.

As estatísticas contam somente jobs MAIN, incluindo arquivos e sessões live;
jobs filhos não duplicam o total. O volume soma `file_size_bytes` das fontes e
não mede espaço ocupado após retenção. Os dados atualizam a cada 30 s e após
ações de manutenção/movimentação. Filtros e seleção são refeitos ao trocar página.

## API

Todas as rotas exigem autenticação e posse no SQL. IDs inexistentes e de outros
usuários recebem o mesmo `404`. A API de leitura existente continua compatível.

| Método / rota | Corpo ou comportamento |
|---|---|
| `GET /projects?include=folders` | Projetos, pastas, contagens e limites. Acrescenta `completed_count`, `cancelled_count`, `total_bytes`. |
| `POST /projects` | `{ "name": "Cliente X" }`; `201` se criado, `200` se existente. |
| `GET /projects/resolve?name=Cliente%20X` | Sempre 200: `{valid, match}`; `match:null` para nome válido novo, ou `{valid:false, error}` para nome inválido. Não cria projeto. |
| `GET /projects/{id}/folders/resolve?name=Audios` | Mesmo contrato para pasta própria; projeto ausente/alheio retorna 404. |
| `PATCH /projects/{id}` | `name`, `description` (inclui `null` para limpar), `archived` opcionais. |
| `DELETE /projects/{id}` | `204` se vazio e sem keys; caso contrário `409`. |
| `POST /projects/{id}/folders` | `{ "name": "Áudios" }`; get-or-add `201`/`200`. |
| `PATCH /folders/{id}` | `{ "name": "ÁUDIOS" }`; mesma identidade normalizada. |
| `DELETE /folders/{id}` | Move os jobs para a raiz e exclui a pasta na mesma transação; `204`. |
| `PATCH /jobs/{id}/location` | `{ "project_id": "…", "folder_id": null }`. |
| `POST /jobs/move` | `{ "job_ids": ["…"], "project_id": "…", "folder_id": null }`; 1–100 IDs, tudo-ou-nada. |

O destino deve existir e estar ativo. Pasta deve pertencer ao projeto do destino.
Mover o job não muda os caminhos/contextos datalake já congelados. A localização
nova filtra a listagem do Ingestify; arquivos externos permanecem no destino original.
ID de job filho é recusado com `422`: mova seu MAIN. IDs repetidos são tratados uma
vez; algum job ausente ou alheio invalida todo o lote. Só metadados de localização
mudam: IDs, resultados, timestamps da execução, tags e paths de objetos permanecem.
`updated_at` registra a alteração normal de metadados.

Limites e get-or-add usam `shared/projects.py`. Não há novas tabelas ou migração
para esta etapa. Locks de destino serializam movimento, criação de pasta,
archive/delete e resolução de uploads; vínculos de API keys revalidam o projeto
e impedem vincular uma key a projeto arquivado.

## Validação

`backend/tests/test_project_management.py` cobre criação/reutilização, limites,
edição cosmética, archive/restore, conflitos de exclusão, autorização, preservação
de dados, atualização de estatísticas, movimentos unitários/em lote e rollback
do lote inválido. Os testes existentes de upload, projetos e live verificam o
reuso das regras anteriores. `frontend/tests/projects-browser.py` exercita a
UI contra fixtures próprias no backend de desenvolvimento; não altera projetos
de usuários existentes.

Para preparar uma conta e dois PDFs sintéticos exclusivos e testar o caminho
real no ambiente de desenvolvimento, com `httpx` e Playwright instalados:

```bash
python frontend/tests/projects-browser.py --url https://dev.ingestify.ai \
  --fixture /tmp/ingestify-projects-validation/state.json --prepare
```

Use um diretório privado novo: o arquivo contém o token e os IDs da conta de
teste. Não o inclua no Git. O runner guarda os handles antes de esperar conversão
e não reenvia arquivos ao observar timeout. O teste mantém os dados para inspeção;
remova somente os jobs/projetos dessa conta ao encerrar. Screenshots e resumo
ficam no mesmo diretório privado.

Validação de 2026-10-05 em `dev.ingestify.ai`: oito cenários Chromium passaram
contra a API real, em desktop e mobile. Dois PDFs sintéticos foram convertidos;
os hashes dos resultados e as tags permaneceram iguais após movimentos e
exclusão de pasta. Estatísticas acompanharam os destinos. Os 210 testes de
projetos/uploads/contrato passaram, assim como o build Next de produção.
Um teste com duas transações MariaDB confirmou que o segundo acesso ao destino
aguarda o primeiro liberar seu lock. As contas e os artefatos criados na
validação foram removidos ao terminar.

Referência de domínio: [spec 0004](../specs/0004-projects-and-folders.md).
