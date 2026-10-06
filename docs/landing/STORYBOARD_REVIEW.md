# Revisão independente do storyboard da home

Revisão inicial: 5 de outubro de 2026. Escopo: [brief](../LANDING_PAGE_BRIEF.md), [galeria](README.md) e inspeção visual dos dezesseis PNGs selecionados em `frontend/public/landing/storyboard/white-rainbow/`, incluindo `scene-05-end-v2.png`.

## Decisão atual — 6 de outubro de 2026

**Storyboard corrigido: APROVADO para produção, com piloto e revisão dos resultados reais.** Não há bloqueio de storyboard pendente nos arquivos [film-manifest.json](film-manifest.json) e [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) revisados. Esta aprovação técnica cobre narrativa, seleção de endpoints, pontes e composição planejada. A instrução do usuário já autoriza o uso da API e a produção da home, com revisão antes de avançar; não há necessidade de uma nova confirmação do proprietário inferida deste parecer. A aprovação não se estende ao filme ainda não gerado, implementação, merge ou publicação.

A correção resolve o problema principal: oito cenas internas são ligadas por sete pontes explícitas, sem eliminar os resultados que precisam ser comparados. A geração pode seguir o piloto previsto no plano, dentro dos limites de cotação de US$ 0,30 por trecho e US$ 4,50 no conjunto. O campo `approval` observado no manifesto ainda registra `pending_storyboard_review_and_owner`; pode ser atualizado para refletir esta aprovação de storyboard. Um gate adicional de proprietário não é exigido por esta revisão.

### Evidência conferida no manifesto

- Quinze trechos em ordem: oito cenas e sete pontes, três segundos cada, total de 45 segundos.
- As quatorze junções consecutivas usam o mesmo caminho exato como último quadro do trecho anterior e primeiro do próximo. Todos os arquivos existem no worktree.
- Todas as cenas e pontes possuem zona de HTML; até 26vw nas cenas e 24vw com texto curto nas pontes. Código previsto abaixo do palco e chamada final expandida somente depois do recolhimento.
- `evolution_label` ativo exatamente em `bridge-06-07`, `scene-07` e `bridge-07-08`. O plano exige sua entrada antes da primeira dessas pontes.
- Cena 5 explicita alternativas inicialmente inativas e ativa apenas o caminho de áudio para o módulo remoto à direita. Documentos e imagens permanecem no destino local.
- Pontes 2→3 e 3→4 identificam novos exemplos, evitando sugerir que PDF vira fala ou que áudio produz recibo. Ponte 5→6 preserva identidade e ordem dos resultados. Pontes de evolução mantêm módulos futuros pontilhados até recolhê-los.
- Exemplos Markdown, transcrição e OCR serão HTML legível; a mídia é ilustrativa. Há uma esfera guia principal e pontos secundários estacionários.
- Composição mobile prevê o quadro horizontal completo em faixa 16:9 e texto separado, sem corte central, com recomposição obrigatória caso a demonstração não permaneça reconhecível. Isso aprova a estratégia vertical; a legibilidade real continua dependente da prévia.

### Riscos para observar no piloto e na mídia

A correspondência de arquivos prova continuidade planejada, não continuidade da geração. Os movimentos de 2→3, 3→4 e 6→7 são os mais complexos para três segundos. Após aprovar a cena 1, convém inspecionar uma dessas pontes cedo, antes de depender do conjunto completo. Se houver fusão, salto ou objeto reconhecível desaparecendo de modo abrupto, corrigir o trecho ou dividi-lo com quadro intermediário; não aprovar uma dissolução que apenas esconda a falha. Qualquer geração adicional deve respeitar os limites acumulados de orçamento do plano; esta aprovação não libera gasto acima deles.

As medidas de HTML incluem a margem esquerda: uma caixa de 26vw somada a padding pode ultrapassar a área livre de 27%. Na prévia, medir o limite direito real da coluna e o maior título, especialmente nas cenas 6 e 8. Isso é critério de composição na implementação, não bloqueio da geração com o manifesto atual.

A estimativa declarada soma US$ 4,29 e os limites declarados somam US$ 4,50. Esta revisão conferiu a consistência do plano, não consultou o preço autenticado nem acessou a credencial. Cotação válida, contrato de API e controle do gasto acumulado continuam sendo responsabilidades do fluxo de produção. Não tratar esse valor como garantia de cobrança final.

O plano informa que o GitHub foi verificado como público durante a preparação. A home deve usar “Ver no GitHub” e retirar o aviso de repositório privado. Este parecer adota essa atualização do responsável pela produção; não fez uma segunda verificação de rede.

## Registro da revisão inicial

Na primeira revisão, a direção visual e a sequência narrativa foram aprovadas, e a produção contínua foi reprovada porque ainda faltavam as sete pontes e regras concretas de composição. Os achados abaixo foram atendidos no planejamento corrigido. Permanecem como critérios de inspeção da mídia e da página, não como bloqueios abertos do storyboard atual.

## Achados por prioridade

### P0 — O fim de cada cena não é o começo da seguinte

Os dezesseis quadros são endpoints internos. Mesmo 1→2, visualmente próximo, muda perspectiva, posição da esfera e regiões destacadas; um corte faz o documento saltar. As demais passagens reorganizam objetos e escalas de modo substancial. Dissolver imagens mascara o corte com objetos duplicados e não executa a continuidade descrita no brief.

**Correção:** planejar quinze trechos ordenados: oito movimentos `start → end` e sete pontes `end(n) → start(n+1)`. Cada encontro deve compartilhar o mesmo arquivo de referência exato. Não reduzir isso a oito movimentos `start(n) → start(n+1)`, pois assim desaparecem os resultados que a pessoa precisa comparar.

### P1 — Texto essencial precisa ser verificável fora da imagem

O fim da cena 2 mostra barras cinzas, não um exemplo de Markdown legível. A cena 3 traz timestamps e formatos, mas as falas também são barras. A cena 4 mostra `42,00`, porém substitui a palavra TOTAL por uma barra no resultado. Os PNGs funcionam como ilustrações; não cumprem sozinhos o objetivo de apresentar pequenos exemplos completos. Rótulos rasterizados podem ainda deformar durante geração.

**Correção:** manter títulos, escopo e exemplos reais em HTML. No período estável de cada saída, exibir um pequeno exemplo legível e identificado como ilustrativo. Não exigir que o modelo gere código, marca, botões ou texto adicional. A legenda OCR deve dizer “Texto extraído e regiões”, sem prometer campos interpretados. A integração/API exige seu bloco de código HTML selecionável, mesmo que o vídeo só mostre uma janela abstrata.

### P1 — Cena 5 precisa mostrar escolha, e cena 7 precisa continuar planejada

A abertura da cena 5 tem duas setas cinzas saindo do áudio. O fim v2 ativa apenas a rota remota, o que é correto. O modelo pode, porém, iluminar ambas durante o movimento. Na cena 7 o PDF se conecta visualmente a servidor e nuvem; fora do contexto, isso sugere roteamento remoto de documentos disponível. Os novos módulos são pontilhados, mas a diferença não basta sem texto.

**Correção:** especificar que as duas rotas iniciais são alternativas inativas; apenas a rota Modal recebe o trabalho de áudio. Documento e imagem continuam locais. Mostrar os rótulos HTML “Workers locais”, “Modal para transcrição” e a nota sobre provider. O rótulo “Visão de evolução” deve entrar antes da ponte 6→7 começar e permanecer até os elementos futuros recolherem na ponte 7→8. Não acrescentar números fictícios de custo, velocidade ou capacidade.

### P1 — A área livre à esquerda diminui nas cenas 6 e 8

Os primeiros quadros reservam aproximadamente um terço da largura para texto. Em `scene-06-end.png`, o painel começa perto de 31% da largura. Em `scene-08-start.png`, o áudio ocupa a região a partir de aproximadamente 27%. Um bloco HTML fixo de 40% invade objetos. O código da cena 6 precisa de mais espaço que um título.

**Correção:** para cada trecho, registrar uma zona segura e validar também seus quadros intermediários. Usar uma coluna HTML curta à esquerda e reduzir a densidade de texto durante as pontes. Código pode aparecer em painel HTML abaixo do palco ou em composição dedicada no trecho de leitura, sem cobrir a origem. Na cena 8, atrasar a expansão do título final até o recolhimento liberar espaço. Não aplicar um véu branco largo que apague os elementos para acomodar texto.

### P1 — A versão vertical ainda é uma entrega distinta

O recorte central de 16:9 elimina metade das comparações e, em alguns quadros, quase todo o conteúdo situado à direita. `object-fit: cover` em um palco vertical não atende ao brief.

**Correção:** entregar composição vertical de fato, com texto acima e os dois lados das transformações visíveis abaixo. Uma montagem vertical pode reutilizar a mídia horizontal completa em uma faixa adequada, sem corte, desde que a leitura seja suficiente; se ficar pequena, será necessária recomposição dos planos. Não declarar mobile concluído apenas porque existe um breakpoint. Manter a alternativa estática com as mesmas informações e ações.

### P2 — A esfera funciona melhor como guia principal, não como personagem único rígido

Os quadros de OCR e execução contêm diversas pequenas esferas nos conectores. Isso diverge da leitura literal de uma única esfera percorrendo toda a história.

**Correção:** identificar nos prompts uma esfera principal acompanhada pela câmera; as demais são pontos estacionários de conexão. Evitar multiplicação espontânea ou troca do guia durante o movimento. Essa interpretação preserva o material aprovado sem exigir regenerar os dezesseis quadros.

## Plano mínimo das pontes

| Ponte | Referências exatas | Ação necessária e cuidado de continuidade |
|---|---|---|
| 1→2 | `scene-01-end.png` → `scene-02-start.png` | Pequena rotação contínua da página; surgimento progressivo dos contornos. Manter identidade da folha, tabela e esfera. |
| 2→3 | `scene-02-end.png` → `scene-03-start.png` | Linha inferior da tabela conduz o olhar; documento e resultado recuam enquanto se revela o eixo de áudio. A esfera precisa viajar da parte inferior direita até a onda, sem teletransporte. Não transformar conteúdo documental em uma transcrição como se fosse a mesma operação. |
| 3→4 | `scene-03-end.png` → `scene-04-start.png` | Contorno de um segmento se desloca e reenquadra como região do recibo; onda e vídeo saem. Fazer uma troca de contexto visível, sem sugerir que a gravação gera o recibo. |
| 4→5 | `scene-04-end.png` → `scene-05-start.png` | Painéis de OCR recuam para o conjunto de resultados; revelar módulos de execução e um novo áudio aguardando rota. Preservar a distinção entre resultado concluído e novo trabalho. |
| 5→6 | `scene-05-end-v2.png` → `scene-06-start.png` | Os três resultados inferiores viram linhas da lista, preservando documento/áudio/recibo nessa ordem; servidores recuam. Evitar que o resultado de áudio se transforme em documento. |
| 6→7 | `scene-06-end.png` → `scene-07-start.png` | Abrir enquadramento, recolher a aplicação/projeto e revelar a visão conceitual de operações e máquinas. Esta é uma mudança real de representação; o rótulo de evolução deve precedê-la. |
| 7→8 | `scene-07-end.png` → `scene-08-start.png` | Recolher os módulos pontilhados antes de reorganizar os formatos ao redor do centro. Não solidificar funcionalidades planejadas como se já fossem atuais. Reservar a esfera central para guiar o encerramento. |

Os endpoints são visualmente muito distantes em 2→3, 3→4 e 6→7. Se o primeiro resultado produzir fusões irreconhecíveis, dividir a ponte em dois movimentos com um quadro intermediário explícito. Quinze trechos são o plano mínimo, não garantia de que uma única geração resolverá cada passagem.

## Orientação para Kling O3 e montagem

O método de primeiro/último quadro é compatível conceitualmente com este storyboard porque define os estados a conectar. Isso não comprova que uma geração preserve todos os objetos ou que a API aceite determinados parâmetros. Verificar o contrato atual da API, o modelo e o suporte a endpoint antes de enviar jobs.

Cada prompt deve limitar-se a um movimento principal, câmera suave, superfície branca estável, mesma geometria de vidro e preservação das formas. Evitar instruções simultâneas demais nas pontes. Gerar sem áudio. Não pedir logos ou texto novo. Registrar, por trecho, modelo efetivo, arquivo inicial/final, duração, resultado e ordem na montagem.

A referência fornecida ao modelo não prova que o primeiro/último quadro do resultado seja idêntico a ela. Inspecionar o vídeo decodificado: geometria, exposição e posição da esfera nos dois lados da emenda. Uma pequena correção de montagem é aceitável se não introduzir salto perceptível; uma dissolução longa entre objetos diferentes não substitui a ponte. Preferir câmera desacelerada em ambos os endpoints para evitar saltos de velocidade.

No mapa de edição, separar momentos de leitura e pontes. Duração de geração não é comprimento de rolagem: o visitante pode receber mais espaço para ler um instante estável sem tornar a câmera lenta demais. Um mapa único deve controlar instante da mídia, capítulo ativo e estado do texto.

## Reversão, acessibilidade e verificação final

O frontend precisa buscar o instante associado à posição de rolagem em qualquer sentido, sem depender de reprodução com velocidade negativa. Ao voltar pelo mesmo ponto, deve mostrar o mesmo quadro e a mesma camada HTML. Evitar partículas com estado próprio, animações de texto por temporizador e efeitos que continuem indefinidamente com a página parada.

Antes de aprovar a publicação, verificar:

- As oito transformações e sete pontes completas, inclusive quadros intermediários, para frente e para trás.
- Parada e inversão no meio de cada ponte; rolagem rápida; saltos por âncora; retorno pelo histórico; redimensionamento.
- Enquadramento desktop e vertical sem cortar origem/resultado; texto legível e sem objetos atrás de código ou ações.
- Mídia indisponível ou lenta: imagem estática contextual, título e links sempre presentes; nenhuma tela preta ou bloqueio de rolagem.
- `prefers-reduced-motion`: seções estáticas, sem trecho fixo longo, com o conteúdo completo e os mesmos destinos.
- Teclado e foco visível; controles reais em HTML; mídia decorativa sem leitura duplicada; estados de disponibilidade, Piloto e Evolução em texto.
- Exemplos de produto corretos: vídeo significa áudio; Modal para transcrição; OCR não promete campos estruturados; GitHub usa o estado público verificado e o destino real.

## Gates restantes

O manifesto com quinze trechos, movimentos das pontes, zonas de HTML, regras de produto e plano vertical foi apresentado e aprovado nesta revisão de 6 de outubro. Para aprovar o filme, apresentar os resultados reais e a revisão das emendas. Para aprovar merge/publicação, apresentar a home renderizada e evidência dos comportamentos acima. Nenhum desses gates pode ser inferido apenas da existência dos PNGs ou do sucesso de um build.
