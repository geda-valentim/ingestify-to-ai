# Revisão da implementação da home

Revisão independente em 6 de outubro de 2026, no worktree `/data/tmp/ingestify/home-worktree`, com preview `http://127.0.0.1:3107`. Arquivos examinados: `frontend/app/page.tsx`, componentes em `frontend/components/landing/`, manifesto, plano de produção e contrato de upload em `backend/api/routes.py`/`projects_api.py`.

## Parecer final — aprovado para merge e publicação

**Aprovado em 6 de outubro de 2026. Não há bloqueios abertos nesta revisão.** O filme final, sua integração com a rolagem e as correções foram conferidos no preview de produção `:3107`; o refinamento final da ponte 6→7 foi conferido no artefato candidato `:3108`, com vídeo real carregado. A publicação deve seguir o processo existente e ainda precisa de verificação pública após o deploy; este parecer não afirma que ela já ocorreu.

### Evidência final

- Quinze trechos reais inspecionados por suas amostras temporais, além de inspeção do filme integrado nos capítulos e pontes. As comparações e mudanças de contexto chegam aos endpoints previstos. A cena 5 encaminha áudio pela linha rainbow até a nuvem, mantendo documentos e imagens locais. A cena 7 mantém os elementos futuros em contorno.
- Dois arquivos H.264, ambos com 45 segundos exatos, 24fps e 1080 frames: desktop 1440×812 / 11.176.064 bytes; mobile 768×434 / 3.506.796 bytes. O retiming elimina o acúmulo de 3,041667s dos arquivos brutos.
- Decodificação completa do filme desktop: 1080 frames, sem frame escuro. Diferença média de luminância nas quatorze emendas entre 0,64 e 2,86 em 255, somada à inspeção visual dos endpoints e navegação em torno das junções.
- Chromium real carregou `video.is-ready` com `readyState=4` e duração de 45s nas viewports 1440×900, 390×667 e 768×1024. A viewport de 390px selecionou o arquivo mobile; as demais, desktop. As provas não foram feitas sobre o fallback PNG.
- Quinze posições percorridas para frente e para trás em desktop e mobile: os frames extraídos por canvas foram idênticos ao revisitar a mesma posição, e a diferença de `currentTime` foi zero. O vídeo permaneceu imóvel após parar a rolagem.
- Quarenta e duas verificações de reversão nas quatorze emendas, antes/depois/antes de cada limite: nenhuma permaneceu em seek após 100ms no ambiente observado. Uma sequência de saltos rápidos estabilizou no último instante pedido.
- Ponte documento→áudio agora anuncia “PRÓXIMO EXEMPLO · ÁUDIO / Agora, uma gravação enviada.” antes da troca visual; a ponte seguinte anuncia uma nova imagem. Na composição final, a troca de exemplos fica explícita e não é apresentada como conversão de PDF em fala.
- O rótulo “VISÃO DE EVOLUÇÃO” permanece nas duas pontes que delimitam a cena de futuro. O título da ponte 6→7 foi elevado para 20%; no candidato `:3108`, seu limite inferior ficou em y310, acima do painel que atravessa a área inferior esquerda. Conferidos os instantes 33,75s, 34,499s e 35,248s.
- A cena de encerramento usa a chamada curta antes do recolhimento e só então apresenta corpo e CTA completos. Os exemplos de documento, áudio e imagem são HTML legível e cabem em 390×667 acima da navegação. A nota “Microfone ao vivo · Piloto” está renderizada.
- Área de transferência com permissão: mensagem “Exemplo copiado.” e 169 caracteres copiados. Negação mostra a alternativa de seleção manual. Entrada direta e retorno de histórico em `/#api` posicionaram a seção em aproximadamente 94,55px, abaixo do cabeçalho.
- Landscape 844×390 usa oito artigos estáticos. Ao voltar para portrait, o vídeo volta a `readyState=4`. Movimento reduzido usa oito artigos e não requisita MP4. Bloqueio de todas as requisições MP4 mantém imagem carregada, título e navegação do capítulo escolhido.
- Nenhum erro JavaScript nas passagens de vídeo observadas. Teclado, foco, âncoras, hierarquia persistente e textos de escopo foram conferidos nas passagens anteriores e preservados nas correções.

### Falha real encontrada e corrigida antes da aprovação

No desktop, o candidato `<source>` mobile não aplicável emitiu um erro que propagou para o handler React do vídeo. O handler removia o elemento antes de carregar a fonte desktop válida, deixando só o fallback. A causa foi isolada capturando o alvo `SOURCE`; o mesmo MP4 isolado carregava normalmente. O handler agora ignora erros cujo alvo não é o próprio vídeo. A aprovação veio após testar novamente o filme efetivamente pronto e reversível nas três viewports.

### Artefatos e alcance

Capturas de inspeção: `/data/tmp/ingestify/review-final/`, incluindo `candidate-3108-bridge11.png`. SHA-256 dos filmes aprovados:

- Desktop: `ca95168ee54e08402d07537cd78d87449ab887507fe6439e314b57f8b43cf444`.
- Mobile: `aa1607902652162ba73c04d88e6bb9731ece137074a7af47b13cbe3014fe59f8`.

A verificação de navegador foi feita com Chromium em ambiente local. Não é um benchmark de rede móvel nem uma certificação de todos os navegadores/dispositivos. O fallback e a versão estática foram exercitados para os casos de mídia indisponível e movimento reduzido.

## Histórico das passagens anteriores

As observações abaixo registram o processo de revisão. Os achados então abertos foram corrigidos e revalidados conforme o parecer final acima.

## Estado da primeira passagem

**Revisão preliminar, sem aprovação para publicação.** A mídia final ainda está em geração; não é possível aprovar fluidez, emendas ou fidelidade dos movimentos pelo fallback estático. Esta passagem avaliou código, conteúdo, layout real, navegação e acessibilidade básica. Nenhum código foi alterado pelo revisor.

## Achados iniciais — resolvidos

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

## Passagem parcial com mídia — cenas 1 a 4

Inspecionados os contact sheets reais dos sete trechos `scene-01`, `bridge-01-02`, `scene-02`, `bridge-02-03`, `scene-03`, `bridge-03-04` e `scene-04`, em `/data/tmp/ingestify/film-production/`. Esta inspeção é de amostras temporais e endpoints; não certifica ainda o comportamento do filme montado no navegador.

As cenas internas mantêm formas reconhecíveis e chegam às comparações esperadas. A ponte 3→4 retira o áudio e introduz o recibo como outro objeto. Na ponte 2→3, a onda aparece dentro do painel ainda rotulado Markdown e conectado ao PDF: o título genérico do capítulo de áudio não elimina sozinho a ambiguidade de origem. Foi solicitado um rótulo explícito de novo exemplo desde o início da ponte. O responsável informou a implementação de “PRÓXIMO EXEMPLO · ÁUDIO” e “Agora, uma gravação enviada.”; a composição final será conferida na próxima passagem. Não há aprovação integral do filme nesta etapa.

Os sete arquivos brutos examinados têm 73 frames a 24fps, duração de 3,041667s. A montagem precisa normalizar a duração ou mapear os tempos reais; concatenar esses arquivos diretamente desalinharia o mapa de 45s. O responsável informou que a montagem faz retiming para três segundos por trecho, preservando os endpoints. Isso será conferido no arquivo final.

As seis emendas disponíveis foram comparadas usando último/primeiro frame decodificado, redimensionado a 480×270. As diferenças médias ficaram entre aproximadamente 1,4 e 3,1 níveis de canal em 255; os endpoints são próximos, mas não idênticos. A pequena média não comprova ausência de salto local ou de velocidade, que continua exigindo revisão na montagem.

### Correções de layout revalidadas no preview de produção

- O título do início da cena 8 passou a ocupar uma coluna menor e não cruza o painel de áudio na captura 1440×900 (`/data/tmp/ingestify/review-home-chapter8-fixed.png`). O P1 de sobreposição está resolvido nessa viewport; quadros intermediários com vídeo ainda serão conferidos.
- Os exemplos HTML dos capítulos de documento, áudio e OCR agora aparecem no momento de resultado em 390×667. Seus limites inferiores foram, respectivamente, y577, y536 e y525, antes da navegação que começa em y612. O P2 de exemplos mobile ocultos está resolvido nessa viewport.
- A nota de microfone piloto foi informada como adicionada pelo responsável, mas aguarda rebuild final para verificação renderizada.
