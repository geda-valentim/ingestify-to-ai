# Revisão da implementação da home

Revisão independente em 6 de outubro de 2026, no worktree `/data/tmp/ingestify/home-worktree`, com preview `http://127.0.0.1:3107`. Arquivos examinados: `frontend/app/page.tsx`, componentes em `frontend/components/landing/`, manifesto, plano de produção e contrato de upload em `backend/api/routes.py`/`projects_api.py`.

## Estado desta passagem

**Revisão preliminar, sem aprovação para publicação.** A mídia final ainda está em geração; não é possível aprovar fluidez, emendas ou fidelidade dos movimentos pelo fallback estático. Esta passagem avaliou código, conteúdo, layout real, navegação e acessibilidade básica. Nenhum código foi alterado pelo revisor.

## Achados abertos

### P1 — Título final invade o painel de áudio antes do recolhimento

Reprodução: viewport 1440×900, botão “Cena 8: Começar”. O texto “Da informação” cruza a borda esquerda do painel de áudio. Screenshot: `/data/tmp/ingestify/review-home-desktop-chapter8.png`.

A coluna em `landing.css` soma `left:4.5%` com `width:25vw`: seu limite real chega a 29,5% da largura. O começo da cena 8 já ocupa a composição a partir de aproximadamente 27%. O plano previa que a chamada final só expandisse quando o recolhimento liberasse espaço, mas o JSX monta imediatamente o título completo assim que o capítulo fica ativo.

Correção recomendada: título curto ou menor enquanto a composição ainda está aberta; expandir apenas no momento de resultado. A alternativa é reservar uma coluna que inclua margem e permaneça inteiramente na área livre, conferindo o maior título e os frames intermediários reais.

### P2 — Exemplos de resultado ocultos durante a experiência mobile

O CSS mobile aplica `display:none` a `.landing-story-copy .landing-result`. A mesma regra vale para desktop baixo. Nos capítulos 2, 3 e 4, a pessoa pode parar no resultado, mas só vê barras decorativas no PNG/vídeo; os exemplos legíveis reaparecem apenas depois de percorrer toda a abertura.

O manifesto/plano promete resultado HTML junto à transformação. Preservar uma versão compacta do exemplo no momento de leitura ou oferecer nessa posição um destino explícito para o exemplo completo. Se o conteúdo não couber com conforto, preferir a composição estática completa nessa faixa de tamanho. O conteúdo não foi perdido da página, mas a demonstração deixa de ser verificável no seu próprio capítulo.

### P2 — Recurso em piloto previsto no brief não aparece

O brief contém uma nota pública “Microfone ao vivo · Piloto”, com ativação pelo operador, capacidade GPU e link `/docs#microfone-live`. A implementação atual não menciona microfone ou piloto em nenhum conteúdo da landing. Não é uma promessa incorreta; é uma parte explícita da home completa que ficou ausente.

Correção recomendada: nota estável e discreta após as operações, com o estado Piloto e o link do brief, sem adicionar outra cena ao filme.

## Achados corrigidos durante a revisão

- **Landscape 844×390:** inicialmente a área sticky tinha altura mínima de 440px mais 72px de cabeçalho. Navegação ficava entre y442 e y512, fora da tela; parte do texto e CTA também era cortada. Após correção do responsável, alturas inferiores a 620px usam modo estático, com resize observado. Revalidado no navegador: oito artigos estáticos, um h1 e largura de página igual à viewport.
- **H1 desaparecia ao trocar de capítulo:** inicialmente havia zero h1 após clicar nas cenas 2–8. O responsável adicionou h1 permanente visualmente oculto e títulos visuais h2. Revalidado ao navegar pelo teclado até Evolução: um h1 permanece no DOM.
- **PNG oculto mudava durante vídeo:** a implementação atual mantém o src do primeiro quadro estável quando a mídia está pronta. Isso evita requisitar dezesseis PNGs atrás do filme. A presença de mídia real ainda precisa ser testada.

## Verificações que passaram nesta etapa

- Viewports 1440×900, 390×844, 390×667 e 768×1024: sem overflow horizontal. Em 390×667, texto e nota de execução cabem acima da navegação.
- Teclado: primeiro foco é “Pular apresentação”; o link pula para o conteúdo normal. Botão de capítulo ativado com Enter conserva o foco e atualiza `aria-current` e título do capítulo.
- Entrada direta por `/#api`: a seção fica a aproximadamente 95px do topo, abaixo do cabeçalho. As âncoras de conteúdo da página funcionam sem depender do filme.
- Movimento reduzido em 390×844: oito artigos estáticos, um h1, nenhum elemento de vídeo e nenhuma requisição MP4 durante a observação.
- Falha de copiar no ambiente do teste mostrou a alternativa “Selecione o código acima para copiar.” O código continua selecionável. Essa observação não certifica o caminho de sucesso da área de transferência.
- Sem mídia final disponível, a imagem inicial e os quadros de capítulos permaneceram visíveis; a falha da mídia não impediu títulos, links ou navegação.
- O mapa `timelineAt` é função da posição, com instante monotônico por trecho e rótulo de evolução nos segmentos 11–13. A rotina guarda o último tempo desejado enquanto há seek e reaplica ao receber `seeked`. Não encontrei nesse exame disparo único ou velocidade negativa como requisito de reversão.

## Fidelidade dos textos ao produto

O exemplo multipart com `file`, `project` e `docling_preset=quality` corresponde aos parâmetros atuais do upload. O endpoint documenta API key via `X-API-Key`. O ambiente de desenvolvimento está identificado junto ao exemplo; não executei upload real.

As limitações principais estão claras: vídeo representa processamento da faixa de áudio; remoto Modal é transcrição; o destino também depende do provider; distribuição geral e composição são evolução; OCR oferece texto e regiões sem prometer campos interpretados. A home usa GitHub público conforme a verificação da preparação. Não encontrei métricas fictícias de custo, precisão ou velocidade, nem garantia universal de retenção.

## Segunda passagem obrigatória com a mídia final

1. Ver os quinze trechos e suas quatorze emendas nos dois sentidos, além de saltos e reversão no meio das sete pontes.
2. Conferir que o instante visível acompanha o texto após seek rápido, sem flash inicial, tela preta ou estado antigo persistente.
3. Inspecionar capítulo 5: apenas áudio na rota Modal; verificar que futuros módulos continuam pontilhados e rotulados durante as pontes de evolução.
4. Verificar leitura dos objetos em 390px e 768px, sobretudo execução e comparação origem/resultado. Se a faixa horizontal ficar pequena demais, recompor a cena ou usar a alternativa estática.
5. Revalidar os achados abertos acima no layout final e testar sucesso de copiar, fallback sob falha de rede, histórico e mudança de orientação.

O build e o manifesto, isoladamente, não encerram essa revisão.
