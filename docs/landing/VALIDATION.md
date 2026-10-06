# Validação da home

## Produção da mídia

- Dezesseis quadros de referência, oito cenas e sete pontes.
- Quinze gerações Higgsfield/Kling O3 Pro, três segundos cada, sem áudio. Cotação total de US$ 4,29; nenhuma regeneração paga.
- Montagem de 45 segundos, 1.080 frames a 24 fps. Desktop 1440×812 / 11.176.064 bytes; celular 768 pixels de largura / 3.506.796 bytes.
- Quadros-chave a cada seis frames, índice MP4 no início e suporte HTTP Range para busca.
- Referências, prompts e hashes: `film-manifest.json`, `film-provenance.json`, `film-joins.json`.

## Verificações

- Build Next.js e TypeScript sem erros, tanto no worktree da branch quanto no contexto de publicação.
- `node frontend/tests/landing-timeline.test.cjs`: navegação entre capítulos, avanço, reversão, limites e rótulo da visão de evolução.
- `frontend/tests/landing-browser.py`, com Playwright/Chromium: vídeo real carregado, busca nos dois sentidos, parada, capítulos, salto da apresentação, cópia do exemplo, FAQ, layouts 1440×900, 390×844, 390×667, 768×1024 e 844×390, movimento reduzido, seleção da mídia mobile e falha de mídia.
- Revisão independente inspecionou os quinze trechos, as emendas e a home renderizada. Conferiu também a igualdade dos frames em quinze posições percorridas na ida e na volta, no desktop e no celular.
- Movimento reduzido e telas com menos de 620px de altura recebem os oito capítulos estáticos. Economia de dados usa a mesma alternativa.
- Microfone ao vivo identificado como piloto; vídeo explicado como fonte de áudio; distribuição geral identificada como visão de evolução; GitHub público conferido.

A revisão encontrou um evento `error` do `<source>` mobile não aplicável no desktop. O handler do `<video>` agora ignora esse evento propagado e permite o carregamento da fonte compatível. O teste de vídeo real cobre esse caso.

Os testes de responsividade usaram viewports de navegador. Não representam validação em todos os aparelhos ou em todas as versões de Safari e Firefox.

## Publicação no ambiente existente

O desenvolvimento usa um worktree isolado e atualizado com `origin/main`, para manter fora do PR as alterações locais de outras tarefas. O ambiente já executava páginas de projetos, documentação por tópico e configurações que ainda tinham alterações locais. A imagem de publicação preserva esse frontend e acrescenta exclusivamente os arquivos da home; essas alterações anteriores não são incorporadas ao PR da home.

O contexto de publicação fica em `/data/tmp/ingestify/release-context/`. A troca é limitada ao serviço `frontend` do Docker Compose existente, usando `--no-deps --no-build`. A imagem anterior é conservada para rollback. O resultado público e a preservação dos demais serviços são verificados depois da troca.
