# Direção de conteúdo e design da home do Ingestify

O Ingestify transforma documentos, imagens, áudio e vídeo em informação utilizável por aplicações de IA. A home deve tornar essa proposta visível em poucos segundos, mostrar as operações disponíveis e explicar o controle sobre sua execução. A ambição é evoluir para uma plataforma open source de operações de transformação, executadas localmente ou de forma distribuída.

Este documento orienta o conteúdo, o design e a implementação da landing page. Os textos públicos propostos aparecem em blocos de citação; as orientações de composição e comportamento acompanham cada seção. O estado das funcionalidades corresponde à documentação consultada em 5 de outubro de 2026. O repositório foi conferido durante a produção e está público; a home usa “Ver no GitHub”.

## Revisão implementada — largura total, SVG e inglês

Esta revisão substitui as instruções anteriores de composição e os textos públicos em português. A home publicada usa inglês, incluindo metadados, navegação, exemplos, FAQ e rótulos acessíveis. A abertura passa a ser “Your files. AI-ready.”. O texto vigente está em `frontend/components/landing/content.ts` e `landing-sections.tsx`.

A página ocupa toda a largura da janela, sem um container central limitado a 1440px. Títulos grandes em preto conduzem a leitura; o filme de vidro líquido permanece como apoio, com opacidade menor, máscara lateral e continuidade nos dois sentidos da rolagem. No celular, o texto fica acima da mídia. Fundo branco, uma seção de execução preta e linhas rainbow preservam a identidade aprovada.

As seções seguintes têm linguagem própria: seletor de documentos/áudio/imagens com transformação em SVG; diagrama de execução local ou Modal; sequência vertical de integração com API; órbitas de linhas na visão open source; encerramento com marca vetorial em largura total. Os exemplos pequenos do SVG têm uma versão HTML legível no celular. Nenhum diagrama simula uma operação real: são exemplos identificados.

As linhas são animadas com traços SVG, o áudio com ondas e o OCR com regiões pulsantes. A entrada dos títulos e o deslocamento de elementos acompanham a rolagem. Loops ficam pausados fora da tela e há controle global para pausar efeitos. Movimento reduzido remove animações e mantém os capítulos estáticos sem baixar o vídeo. Conteúdo permanece visível sem JavaScript.

A disponibilidade continua explícita: Modal é opcional para transcrição; microfone é piloto; execução distribuída geral e composição de operações são evolução planejada. O GitHub permanece acessível pela navegação e pela seção do projeto.

## Posicionamento

**Definição do produto**

> Uma plataforma para transformar documentos, imagens, áudio e vídeo em dados para IA, com controle sobre o processamento e os resultados.

**Promessa central**

> Seus arquivos se tornam informação que suas aplicações podem usar.

O público inicial são desenvolvedores, equipes de produto e pessoas que automatizam rotinas com IA. Eles precisam extrair informação de arquivos, integrar o processamento a outros sistemas e entender onde cada trabalho está rodando.

A home deve responder, nesta ordem: o que posso transformar, o que recebo, como uso e onde posso executar. A proposta open source fecha essa narrativa com a direção de evolução e um caminho claro para o GitHub.

A linguagem deve ser direta e concreta. Use “transcrever uma gravação”, “extrair texto de uma imagem” e “converter um PDF”. Termos como workers, modelos e roteamento entram quando ajudam a explicar uma escolha. A página deve transmitir utilidade, cuidado com a informação e clareza operacional.

## Direção visual

A home será uma experiência cinematográfica controlada pela rolagem. Ao descer, o visitante avança por um filme que mostra arquivos se transformando em informação; ao subir, percorre os mesmos quadros em sentido inverso. Ao parar, a imagem permanece naquele ponto. O próprio produto fornece os elementos visuais da narrativa.

Use fundo branco, superfícies brancas e transparentes, texto preto e detalhes em cinza. A referência de linguagem é a clareza geométrica de Vercel e Next.js, mantendo a identidade do Ingestify. Linhas finas em rainbow atravessam a composição e acompanham os dados; reflexos prismáticos discretos aparecem nas bordas do vidro líquido. O branco domina o quadro. Estados e destinos se distinguem por rótulos, ícones e formas, sem depender de uma cor. Valide o contraste na implementação.

A tipografia principal deve ter boa leitura e títulos amplos, com pesos bem definidos. Use uma fonte monoespaçada apenas para nomes de arquivos, trechos de código, formatos e eventos de processamento. O espaçamento generoso e a hierarquia devem sustentar a composição.

O elemento de maior destaque será um palco visual que permanece na tela durante os capítulos da narrativa. Arquivos, regiões de texto, ondas de áudio e unidades de execução se reorganizam dentro do mesmo espaço. A continuidade entre os objetos deve conectar as cenas. Títulos, explicações e botões ficam em uma camada HTML sobreposta, com áreas reservadas para leitura.

A estética combina profundidade discreta, vidro líquido incolor com bordas suaves, refração e sombras leves sobre branco. O movimento deve transmitir precisão: aproximação de câmera, separação de camadas, alinhamento de texto e passagem de dados entre destinos. O rainbow fica nas linhas em movimento e em reflexos localizados; evite preencher painéis ou o fundo com gradientes coloridos. A tipografia e os controles permanecem pretos.

Evite imagens genéricas de robôs, cérebros e circuitos. Também dispense números decorativos, depoimentos fictícios, estrelas de GitHub e gráficos sem dados reais. Modelos e ferramentas podem ser citados como tecnologias utilizadas, sem sugerir parceria ou endosso.

## Estrutura da página

| Ordem | Seção | Objetivo |
|---|---|---|
| 1 | Navegação e apresentação | Explicar a proposta e dar acesso ao produto e aos docs. |
| 2 | Operações disponíveis | Mostrar entradas e resultados concretos. |
| 3 | Execução e capacidade | Explicar processamento local e uso opcional da nuvem. |
| 4 | Organização e acompanhamento | Mostrar o trabalho depois do envio do arquivo. |
| 5 | Integração por API | Demonstrar como incorporar uma operação a uma aplicação. |
| 6 | Evolução e abertura do código | Apresentar a visão e o estado do GitHub. |
| 7 | Perguntas frequentes | Resolver dúvidas sobre execução, vídeo e disponibilidade. |
| 8 | Chamada final e rodapé | Conduzir para documentação, acesso e repositório. |

As seções 1 a 6 se desenvolvem nos capítulos do filme descritos abaixo. Seu conteúdo deve aparecer junto às cenas correspondentes, evitando repetir toda a narrativa em uma segunda sequência de blocos. Depois do filme, as perguntas frequentes e a chamada final seguem na rolagem normal.

## Filme controlado pela rolagem

Os [quadros de início e fim das oito cenas](landing/README.md) estão gerados na direção branca, preta e rainbow, com vidro líquido transparente. A galeria reúne as 16 imagens selecionadas; os [prompts e caminhos dos arquivos](landing/image-prompts.json) acompanham o material. A cópia local fica em `/data/tmp/ingestify/white-rainbow/`, e os arquivos versionados em `frontend/public/landing/storyboard/white-rainbow/`.

### Conceito e continuidade

O fio condutor é uma pequena esfera de vidro líquido que percorre uma linha espectral rainbow: começa na borda de um arquivo, percorre seu conteúdo, identifica um resultado e conduz a câmera ao próximo contexto. Seu papel é orientar o olhar. Os arquivos mantêm forma e identidade reconhecíveis durante cada transformação.

O cenário é um espaço branco contínuo, com profundidade, sombras suaves e chão branco. Os painéis são de vidro líquido transparente, com conteúdo preto e refração discreta. A câmera faz deslocamentos curtos e aproximações suaves. Cada cena termina com um elemento cuja posição, escala e direção de movimento já preparam o início da seguinte. O movimento inverso deve preservar essas mesmas correspondências.

Todo o filme representa exemplos ilustrativos. Recuar a rolagem revisita a demonstração; não cancela jobs nem desfaz operações reais. O vídeo não tem áudio e não começa a tocar sozinho. Uma indicação inicial discreta informa: “Role para explorar”.

O manifesto de produção em [film-manifest.json](landing/film-manifest.json) é a fonte exata para tempos e pontes: 15 trechos de três segundos, com leitura prolongada nos resultados por mapeamento da rolagem. Os percentuais abaixo orientaram o roteiro inicial.

### Mapa da narrativa

Os percentuais representam a posição ao longo do trecho cinematográfico, do início ao fim. A duração do arquivo de vídeo será definida na produção; o visitante determina o ritmo de exibição pela rolagem.

| Cena | Trecho | Assunto | Imagem de chegada |
|---|---|---|---|
| 1 | 0 a 10% | Entradas | Um PDF se aproxima entre arquivos de áudio, imagem e vídeo. |
| 2 | 10 a 25% | Documentos | Documento e Markdown ficam lado a lado. |
| 3 | 25 a 40% | Áudio e vídeo | Uma onda de áudio se alinha a segmentos de transcrição. |
| 4 | 40 a 52% | Imagens | Regiões de uma imagem se conectam ao texto extraído. |
| 5 | 52 a 70% | Execução | Um trabalho de áudio tem caminhos local e Modal visíveis. |
| 6 | 70 a 82% | Organização e API | Resultados entram em um projeto e se conectam a uma aplicação. |
| 7 | 82 a 94% | Evolução | A composição revela futuras conexões entre máquinas e operações. |
| 8 | 94 a 100% | Encerramento | Os elementos se recolhem e dão espaço à marca e ao próximo passo. |

### Cena 1 Entrada no universo dos arquivos

**Início:** fundo branco com o título principal e as ações já legíveis. À direita, um documento inclinado em perspectiva ocupa o primeiro plano. Uma forma de onda, um recibo e uma miniatura de vídeo aparecem ao fundo, separados por profundidade. O primeiro quadro precisa funcionar como imagem estática de apresentação.

**Movimento:** conforme a pessoa rola, os quatro arquivos se aproximam e se alinham. A esfera de vidro líquido toca a borda do PDF. A câmera acompanha esse arquivo e revela seu título, um parágrafo e uma tabela. Os outros formatos recuam para a periferia do palco.

**Fim:** o PDF está quase frontal, com conteúdo reconhecível, e ocupa a área visual principal. A esfera está no topo da página, pronto para percorrê-la.

**Transição:** a mesma página permanece na mesma posição quando começa a cena 2. A aproximação desacelera e dá lugar à leitura das camadas do documento.

**Texto sobreposto:** “Transforme seus arquivos em dados para IA.” As ações iniciais ficam utilizáveis durante a apresentação. O título se recolhe antes de entrar a explicação da próxima operação.

### Cena 2 Documento em informação estruturada

**Início:** o PDF da cena anterior está enquadrado de frente. Título, parágrafo e tabela têm formas visualmente distintas.

**Movimento:** o marcador percorre a página e destaca essas regiões. As camadas se afastam poucos pixels do papel e deslizam para a direita, onde se alinham como título, texto e tabela em Markdown. A folha original continua visível à esquerda para permitir a comparação. No plano de fundo, duas páginas adicionais se separam e chegam a uma sequência ordenada, sugerindo o processamento por página.

**Fim:** origem e resultado estão lado a lado, em um enquadramento estável. O visitante pode parar e ler um pequeno exemplo completo. O indicador “Markdown” identifica a saída.

**Transição:** depois desse momento de leitura, a câmera acompanha uma linha horizontal da tabela. A linha atravessa o quadro e se transforma no eixo de uma forma de onda. O PDF se afasta; a onda continua exatamente no mesmo alinhamento para abrir a cena de áudio.

**Texto sobreposto:** “Do documento ao Markdown.” Complemento: “Texto, tabelas e estrutura para o próximo passo da sua aplicação.” Link: “Ver conversão de documentos”.

### Cena 3 Gravação em transcrição

**Início:** o eixo vindo da tabela sustenta uma forma de onda. Uma pequena miniatura de vídeo aparece ligada à sua faixa de áudio, identificando a origem sem sugerir análise visual das cenas.

**Movimento:** o marcador percorre a onda. Intervalos selecionados se alinham a blocos de transcrição com timestamps. Os blocos se organizam em duas linhas legíveis. As opções TXT, JSON e VTT aparecem como diferentes representações do mesmo resultado. A onda se revela conforme a rolagem, sem pulsação automática quando o visitante para.

**Fim:** forma de onda acima, transcrição abaixo e formatos de saída ao lado. Uma linha de legenda é destacada junto ao intervalo correspondente.

**Transição:** a linha de legenda recebe um contorno retangular. A câmera se aproxima desse contorno enquanto a onda desaparece. O retângulo passa a enquadrar uma linha impressa no recibo da próxima cena, preservando posição e proporção.

**Texto sobreposto:** “Da gravação ao texto.” Complemento: “Transcrição, timestamps e legendas a partir de áudio e vídeo.” Nota próxima: “Vídeo: processamento da faixa de áudio.”

### Cena 4 Imagem em texto e regiões

**Início:** o contorno da cena anterior agora envolve uma linha de um recibo. A câmera recua o suficiente para revelar a imagem inteira.

**Movimento:** outras regiões recebem contornos discretos. Linhas curtas conectam cada região ao texto correspondente em um painel ao lado. Um exemplo como “TOTAL 42,00” aparece como texto extraído, sem se converter em um formulário de campos interpretados. Um seletor visual secundário pode indicar “Descrição” como outra operação disponível, sem competir com a demonstração principal de OCR.

**Fim:** imagem, regiões e texto extraído formam uma composição limpa. O visitante identifica claramente de onde saiu cada trecho.

**Transição:** o painel se reduz e recebe uma moldura de trabalho concluído. A câmera se afasta para revelar uma fila com trabalhos de documento, imagem e áudio. A esfera passa para um novo trabalho de áudio, ainda aguardando execução, que será o protagonista da cena 5.

**Texto sobreposto:** “Da imagem à informação.” Complemento: “Extraia texto com suas regiões ou gere uma descrição pela API.”

### Cena 5 Escolha do local de execução

**Início:** a fila ocupa o centro. À esquerda, um módulo discreto representa os workers locais. À direita, um módulo de vidro com símbolo de nuvem representa o Modal. O trabalho de áudio está pronto para ser encaminhado; resultados já concluídos ficam visualmente separados.

**Movimento:** primeiro se ilumina o caminho local. Trabalhos de documento e imagem permanecem associados a esse destino. Em seguida, uma regra de espera aparece junto ao trabalho de áudio e o caminho até o Modal é revelado. O áudio percorre esse caminho como exemplo de uma rota configurada. Indicadores textuais de capacidade e orçamento acompanham o módulo remoto, sem valores inventados.

**Fim:** os dois destinos estão visíveis. O resultado da transcrição remota retorna ao conjunto de resultados. Os rótulos “Workers locais” e “Modal para transcrição” permanecem legíveis e deixam claro o escopo de cada caminho.

**Transição:** os trajetos se aproximam em perspectiva e seus pontos de chegada se alinham. Os resultados passam a formar as linhas de uma lista de jobs. A câmera segue o resultado de áudio até sua posição nessa lista.

**Texto sobreposto:** “Escolha onde o trabalho acontece.” Complemento: “Execução local e transcrição no Modal, conforme capacidade, prioridade e orçamento configurados.” Nota: “O destino dos dados também depende do provider utilizado.”

Não represente o mesmo job rodando nos dois destinos ao mesmo tempo. O trecho ilustra uma escolha de rota. Ao voltar a rolagem, a animação apenas revisita essa escolha.

### Cena 6 Resultados dentro da rotina

**Início:** os resultados da cena anterior estão alinhados em uma lista com nomes de arquivo, operação e status. Uma moldura de projeto aparece ao redor da lista.

**Movimento:** a câmera recua e revela projeto, pasta e tags. Um job abre seu detalhe e o resultado aparece ao lado da origem. Em seguida, a composição se desloca para reservar espaço a um exemplo curto de API, com a sequência “Enviar → acompanhar → obter resultado”. Uma linha liga o resultado a uma janela simples identificada como “Sua aplicação”.

**Fim:** organização e integração dividem o palco: projeto de um lado, operação acessível por API do outro. O exemplo de código é HTML selecionável, e o botão de copiar permanece utilizável durante o momento de leitura.

**Transição:** a janela da aplicação e o projeto se reduzem, mantendo a conexão entre eles. A câmera abre o enquadramento e revela espaço para novos módulos. Antes que novos elementos apareçam, entra o rótulo “Visão de evolução”.

**Texto sobreposto:** “Cada trabalho tem seu lugar.” Depois: “Uma operação do Ingestify dentro da sua aplicação.” Os dois textos se alternam em momentos distintos, com pausa visual para leitura.

### Cena 7 Evolução para operações distribuídas

**Início:** a estrutura disponível hoje continua sólida no centro, acompanhada do rótulo “Visão de evolução”.

**Movimento:** contornos de outras máquinas aparecem ao redor e se conectam por linhas pontilhadas. Em outra parte do mesmo quadro, módulos de operações se alinham em uma sequência, sugerindo futura composição de etapas. Mantenha poucos elementos grandes e compreensíveis, sem uma nuvem de partículas ou uma rede excessivamente complexa.

**Fim:** a imagem apresenta um sistema que pode crescer a partir da base atual. Os componentes futuros mantêm tratamento de contorno pontilhado e legendas “Conectar outras máquinas” e “Compor operações”. A condição planejada continua visível durante todo esse trecho.

**Transição:** as linhas externas retornam em direção ao centro conforme a câmera se afasta. Os módulos se organizam ao redor de um plano central vazio, preparando a entrada da marca. O movimento pode lembrar a construção coletiva de uma plataforma, sem representar o GitHub como provedor de execução.

**Texto sobreposto:** “Uma plataforma construída para evoluir com a comunidade.” Complemento: “Mais operações, conexão entre máquinas e fluxos reutilizáveis.” O link “Ver no GitHub” leva ao repositório público.

### Cena 8 Marca e próximo passo

**Início:** os módulos estão organizados em torno do centro. A esfera de vidro líquido completa seu percurso e se posiciona perto da marca.

**Movimento:** a câmera desacelera. As linhas rainbow perdem intensidade e os elementos se recolhem até restar uma composição simples com a marca Ingestify e pequenos símbolos dos formatos de entrada. A escala da marca permanece confortável, sem ocupar a tela inteira.

**Fim:** quadro estável com espaço para “Comece pela transformação que você precisa.” O botão “Explorar a documentação” e o link do GitHub ficam disponíveis. Ao continuar descendo, o palco deixa de ficar fixo e sai normalmente da tela, abrindo as perguntas frequentes e a chamada final.

**Transição para o restante da página:** o fundo e as margens se mantêm iguais aos da seção seguinte, sem corte de cor ou salto de rolagem. Ao subir novamente, a pessoa reencontra esse mesmo quadro final e o filme recua a partir dele.

### Ritmo e reversão

Cada cena deve reservar aproximadamente o primeiro quinto de seu trecho para a entrada, a parte central para transformação e leitura, e o trecho final para preparar a próxima imagem. As proporções são orientações de montagem; os momentos com código e comparação entre entrada e saída precisam de mais espaço de leitura.

Todo estado visual depende da posição da rolagem. Movimento, opacidade, câmera, texto e capítulo ativo devem retornar ao mesmo estado quando o visitante revisita uma posição. Evite disparos que só funcionem uma vez, frases digitadas com temporizador e partículas aleatórias que mudem ao voltar.

Não use reprodução com velocidade negativa como requisito da experiência. O objetivo é selecionar o instante correspondente à rolagem em qualquer direção, com estabilidade nos quadros de chegada. Ao parar de rolar, qualquer suavização deve terminar rapidamente e o quadro deve ficar imóvel.

O vídeo não deve sequestrar a roda do mouse, criar aceleração própria ou impedir a rolagem normal por toque e teclado. Links de navegação levam à posição real do capítulo; entrar diretamente por uma âncora precisa mostrar o quadro e o texto corretos.

### Composição do vídeo e das camadas de interface

O vídeo fornece câmera, objetos, iluminação e transformações. Títulos, legendas de escopo, código, links, botões e avisos de disponibilidade devem ser elementos HTML. Reserve zonas livres para essas camadas em todas as cenas, inclusive nos quadros intermediários.

No desktop, alterne o foco visual entre centro e lateral direita, mantendo uma área tranquila à esquerda para explicação. Faça as trocas de texto nos momentos de menor deslocamento. No celular, use uma composição vertical própria: texto acima e transformação abaixo, preservando a relação entre origem e resultado. Um corte central do filme horizontal não basta quando elimina um dos lados da demonstração.

A produção deve entregar um filme horizontal e uma versão vertical com a mesma ordem de cenas, os quadros inicial e final de cada capítulo, imagens estáticas de fallback e um mapa que relacione os capítulos aos instantes do vídeo. Cada transição precisa ser revisada para frente, para trás e em saltos entre capítulos.

A técnica final de exibição deve ser escolhida após um protótipo com o filme: vídeo com busca por instante ou sequência de quadros, conforme a fluidez e o custo de carregamento observados. Ambas devem preservar a mesma experiência de rolagem reversível. Não carregar todos os quadros de uma sequência de alta resolução de uma só vez.

### Carregamento e experiência alternativa

O primeiro quadro e os textos da apresentação aparecem antes da mídia completa. O carregamento ocorre progressivamente, priorizando o capítulo atual e seus vizinhos. Se o visitante rolar antes de a mídia estar pronta, o texto continua acompanhando a página e a imagem estática do capítulo oferece contexto. Falha de carregamento não pode deixar uma área vazia ou bloquear os links.

Com movimento reduzido, apresente quadros estáticos dos capítulos em seções normais, sem câmera em movimento e sem um longo trecho de palco fixo. A mesma alternativa atende dispositivos nos quais a experiência cinematográfica não atingir fluidez aceitável. O conteúdo e as ações permanecem disponíveis.

Antes de publicar, conferir rolagem lenta, rápida, reversão no meio de cada transição, salto por âncora, redimensionamento, orientação do celular e retorno pelo histórico. Não pode haver telas pretas entre cenas, desencontro persistente de texto e imagem ou conteúdo essencial que só seja legível enquanto se move.

## Navegação

À esquerda, a marca Ingestify. No centro, os links “Operações”, “Execução” e “Código aberto”, apontando para seções da página. À direita, “Documentação”, “GitHub” e a ação “Entrar”.

O GitHub deve ter o indicador visível “Privado”. No celular, mantenha a marca e “Entrar” visíveis e reúna os demais links em um menu acessível.

A home deve ser pública. Atualmente, a rota raiz encaminha o visitante para login ou dashboard; a implementação da landing deve substituir esse comportamento. Usuários autenticados podem ver “Abrir painel” no lugar de “Entrar” e continuar acessando a apresentação.

## Apresentação principal

**Texto de apoio acima do título**

> Documentos · Imagens · Áudio · Vídeo

**Título principal**

> Transforme seus arquivos em dados para IA.

**Descrição**

> Converta documentos em Markdown, transcreva gravações e extraia texto de imagens. Organize seus trabalhos e acompanhe o processamento em uma plataforma com API e execução local. Use GPUs na nuvem para transcrição quando precisar.

**Ações**

- Principal: “Explorar a documentação”, com destino em `/docs`.
- Secundária: “Ver operações”, com destino em `#operacoes`.

**Nota próxima às ações**

> Construindo uma plataforma aberta. Acompanhe o código no GitHub.

No desktop, reserve o lado esquerdo para o texto e as ações da apresentação e use o restante para o primeiro quadro do filme. No celular, apresente a promessa e os botões acima da composição vertical. O primeiro contato deve funcionar antes de qualquer rolagem ou carregamento do vídeo completo.

### Demonstração de transformação

As cenas de documento, áudio e imagem formam a demonstração principal, percorrida pela rolagem. Um indicador discreto de capítulos pode oferecer atalhos para as posições correspondentes. Esses atalhos movem a página até a cena e mantêm a mesma linha do tempo.

| Capítulo | Entrada ilustrativa | Operação | Resultado ilustrativo |
|---|---|---|---|
| Documento | `relatorio.pdf`, com título, parágrafo e tabela | Conversão de documento | Trecho em Markdown preservando esses elementos. |
| Áudio | `reuniao.mp3`, com uma forma de onda | Transcrição | Duas falas com timestamps e opções TXT, JSON e VTT. |
| Imagem | `recibo.png`, com valores legíveis | OCR | Texto extraído e regiões destacadas na imagem. |

O visitante deve conseguir comparar a origem e a saída. Todo o conteúdo deve ser sintético e identificado como “Exemplo ilustrativo”. A demonstração deve funcionar sem conta e sem disparar inferência real. Ela não deve exibir controles de upload que aparentem enviar arquivos.

As transições seguem o roteiro do filme. O conteúdo final precisa permanecer disponível na versão estática com movimento reduzido. Não use durações, custos ou percentuais de precisão fictícios.

## Operações disponíveis

Âncora sugerida: `operacoes`.

**Título**

> Operações que fazem parte do seu dia a dia.

**Introdução**

> Prepare documentos para uma base de conhecimento, transforme gravações em texto e extraia informação de imagens. Escolha a operação e use o resultado no seu próximo passo.

Distribua os textos abaixo pelas cenas 2, 3 e 4, junto aos exemplos de saída correspondentes. Na experiência estática, apresente-os em três seções com imagens dos respectivos resultados.

### Documentos

> **Do documento ao Markdown.**
>
> Converta PDFs e documentos compatíveis em texto estruturado. Escolha presets para extração de imagens e OCR e acompanhe o processamento de PDFs por página.

Formatos em destaque: PDF, DOCX, HTML, PPTX e XLSX. O suporte depende da versão instalada do conversor; a lista completa e seus limites ficam nos docs.

Ação: “Ver conversão de documentos” → `/docs#documentos`.

### Áudio e vídeo

> **Da gravação ao texto.**
>
> Transcreva arquivos de áudio e a faixa de áudio de vídeos. Consulte trechos durante o processamento e obtenha texto, segmentos com timestamps e legendas.

Saídas em destaque: Markdown, TXT, JSON, VTT e SRT. “Vídeo” significa transcrição da faixa de áudio; análise das cenas não faz parte dessa oferta.

Ação: “Ver transcrição” → `/docs#transcribe`.

### Imagens

> **Da imagem à informação.**
>
> Extraia texto com suas regiões na imagem ou gere uma descrição do conteúdo visual. Integre OCR e descrição às suas aplicações pela API.

Mostre uma região destacada no exemplo de recibo e o texto correspondente. Evite sugerir extração pronta de campos como CNPJ, subtotal e impostos: OCR fornece o texto e suas regiões, e a interpretação em campos é outro passo.

Ação: “Ver operações de imagem” → `/docs#imagens`.

### Recurso em piloto

Em uma nota complementar após as operações principais, fora do filme ou em uma área estável da interface:

> **Microfone ao vivo · Piloto**
>
> Capture áudio e acompanhe legendas enquanto fala. Disponível mediante ativação pelo operador e capacidade GPU, com validação para produção em andamento.

Ação: “Conhecer o piloto” → `/docs#microfone-live`.

## Execução e capacidade

Âncora sugerida: `execucao`.

**Título**

> Escolha onde o trabalho acontece.

**Introdução**

> Use workers locais para processar seus arquivos. Para transcrição, configure também contas Modal e defina a prioridade de execução, a capacidade e os limites de orçamento.

Use a composição da cena 5, com uma fila de trabalhos ao centro e dois destinos: “Workers locais” e “Modal para transcrição”. Identifique documentos, imagens e áudio no destino local; no destino Modal, apenas áudio.

| Destino | Texto público |
|---|---|
| Execução local | “Use CPU ou GPU disponível no seu ambiente, conforme a operação e a configuração.” |
| Transcrição na nuvem | “Encaminhe transcrições para GPUs no Modal conforme as regras configuradas.” |
| Controle operacional | “Acompanhe capacidade, tentativas e orçamento dos motores remotos.” |

**Exemplo de regra**

> Primeiro, meus workers locais. Depois, Modal quando a espera atingir o limite que configurei.

Identifique essa frase como exemplo de configuração. A representação não deve sugerir provisionamento automático de servidores, escolha automática da melhor GPU ou custo garantido.

**Nota pública de escopo**

> Hoje, a execução remota via Modal atende transcrição de arquivos. Documentos e imagens usam rotas locais. O destino dos dados também depende do provider configurado.

Ação: “Entender os motores de execução” → `/docs#compute`.

A conexão simplificada de outras máquinas deve aparecer na seção de evolução. A visualização desta seção representa o funcionamento disponível.

## Organização e acompanhamento

**Título**

> Cada trabalho tem seu lugar.

**Descrição**

> Organize seus arquivos em projetos e pastas, adicione tags e acompanhe os jobs. Para PDFs divididos, consulte páginas já concluídas e reenvie páginas que falharam.

Use a prévia compacta da interface na cena 6, com projeto, arquivo, operação e status. Prepare os elementos a partir da interface real com dados de demonstração. Identifique a composição como ilustrativa e limite-a a comportamentos existentes.

Três detalhes podem acompanhar a prévia:

- “Projetos e pastas para organizar suas rotinas.”
- “Status e progresso para acompanhar o processamento.”
- “API keys para integrar seus sistemas.”

Evite apresentar armazenamento permanente de todo resultado como uma garantia geral. Retenção e recuperação ainda diferem entre operações e precisam seguir a documentação de cada uma.

## Integração por API

**Título**

> Uma operação do Ingestify dentro da sua aplicação.

**Descrição**

> Envie um documento ou uma gravação, receba o identificador do job e acompanhe sua conclusão. Use sua API key para integrar o processamento aos seus scripts e serviços.

Na segunda parte da cena 6, apresente um exemplo curto de envio de documento em HTML, com botão de copiar:

```bash
curl -X POST "https://dev.ingestify.ai/api/upload" \
  -H "X-API-Key: SUA_CHAVE" \
  -F "file=@relatorio.pdf" \
  -F "project=Documentos" \
  -F "docling_preset=quality"
```

Abaixo do código, mostre a sequência de uso: “Enviar arquivo → acompanhar job → obter resultado”. O ambiente `dev.ingestify.ai` deve ser identificado como desenvolvimento, com necessidade de uma conta e API key válidas.

**Complemento**

> As operações de imagem aguardam o resultado na própria requisição. Consulte os contratos e limites de cada operação na documentação.

Ações: “Ler a documentação” → `/docs` e “Abrir referência da API” → `/api/docs`.

O código da landing precisa acompanhar o contrato real da API. Não apresente SDK próprio, webhook de conclusão ou comando de instalação enquanto esses recursos não estiverem disponíveis e documentados.

## Evolução e abertura do código

Âncora sugerida: `codigo-aberto`.

**Título**

> Uma plataforma construída para evoluir com a comunidade.

**Descrição**

> A visão do Ingestify é tornar operações de transformação para IA reutilizáveis e acessíveis. Executar na sua máquina, distribuir o trabalho entre seus servidores e recorrer à nuvem quando fizer sentido.
>
> O repositório está público. Explore o funcionamento, acompanhe as operações e consulte as condições de uso e contribuição nos arquivos do projeto.

Na cena 7, mantenha a base atual e a direção de evolução visualmente distintas, conforme os grupos abaixo. Esses grupos orientam os rótulos da cena; a tabela completa pode ser usada na experiência estática, sem datas de entrega.

| Disponível hoje | Direção de evolução |
|---|---|
| Conversão de documentos, transcrição e operações de imagem. | Contrato comum para adicionar e versionar operações. |
| Workers locais e transcrição remota via Modal. | Conexão mais simples de outras máquinas e execução distribuída. |
| Projetos, jobs, API e controles de execução. | Composição de operações em fluxos reutilizáveis. |

### Link do GitHub

Destino confirmado pelo remote do projeto: [github.com/geda-valentim/ingestify-to-ai](https://github.com/geda-valentim/ingestify-to-ai).

**Texto do link**

> Ver no GitHub

O link abre o repositório público real. A disponibilidade do código não substitui a licença e as instruções de contribuição; consulte os arquivos do projeto.

## Perguntas frequentes

**O Ingestify já é open source?**

> O código está disponível no GitHub. A visão é uma plataforma open source; consulte a licença e as condições de uso nos arquivos do projeto.

**Posso executar no meu ambiente?**

> A arquitetura suporta workers locais em CPU e GPU. Os requisitos variam conforme a operação e os modelos utilizados.

**Preciso de uma GPU?**

> As operações em lote podem usar CPU ou GPU conforme a configuração. O desempenho depende do arquivo, do modelo e do hardware. O piloto de microfone ao vivo exige capacidade GPU.

**Todos os arquivos podem ser processados na nuvem?**

> O adapter Modal atual atende transcrição de arquivos. As rotas de documentos e imagens são locais.

**Meus arquivos ficam sempre no meu servidor?**

> Isso depende da configuração. Modelos executados no próprio ambiente permitem processamento interno; providers de API externa e execução remota transferem os dados necessários para esses serviços. Confira o provider e a rota utilizados.

**O que o Ingestify faz com vídeos?**

> Atualmente, transcreve a faixa de áudio e produz texto e legendas. A análise das cenas do vídeo não faz parte dessa operação.

## Chamada final e rodapé

**Título**

> Comece pela transformação que você precisa.

**Descrição**

> Explore as operações, conheça a API e veja como o Ingestify pode entrar na sua rotina.

Botão principal: “Explorar a documentação” → `/docs`.

Link secundário: “Entrar na plataforma” → `/login`. Para usuários autenticados, “Abrir painel” → `/dashboard`.

O rodapé reúne marca, documentação, referência da API, acesso à plataforma e link para o GitHub público. O cadastro não deve ser uma chamada fixa, pois depende da configuração de registro do ambiente.

## Comportamento e adaptação

No celular, as cenas seguem a mesma narrativa com composição vertical e nenhum texto essencial oculto. A altura do trecho cinematográfico deve ser ajustada para oferecer leitura confortável sem exigir rolagem excessiva. Na alternativa estática, use seções em uma coluna. Blocos de código podem ter rolagem horizontal própria; o restante da página deve caber na tela.

Os atalhos entre capítulos e as perguntas frequentes devem funcionar por teclado, com foco visível. Estados como “Piloto” e “Privado” precisam de rótulos textuais. Respeite a preferência por movimento reduzido com a experiência estática descrita no roteiro. A camada visual decorativa não deve duplicar a leitura do conteúdo pelos leitores de tela.

O vídeo é o elemento central da experiência e deve ser sincronizado à rolagem nos dois sentidos. Carregue primeiro o quadro de apresentação e mantenha os textos e as ações disponíveis durante a preparação da mídia. A página deve abrir sem chamadas de inferência, autenticação ou acesso ao GitHub.

Os links internos de documentação deste documento usam as âncoras atualmente publicadas em `/docs`. Se a documentação por tópico for publicada antes da landing, atualize os destinos e preserve redirecionamento ou compatibilidade com as âncoras existentes.

## Metadados sugeridos

**Título da página**

> Ingestify | Transforme seus arquivos em dados para IA

**Descrição para busca e compartilhamento**

> Converta documentos, transcreva áudio e extraia texto de imagens. Conheça a API do Ingestify, os workers locais e a transcrição na nuvem.

A imagem de compartilhamento deve reproduzir a marca, a promessa central e um exemplo de documento convertido. Evite incluir status, métricas ou telas ilegíveis em tamanho pequeno. Configure a URL canônica de acordo com o domínio em que a landing for efetivamente publicada.

## Critérios para a implementação

A landing estará pronta quando um visitante conseguir identificar as operações disponíveis, entender seus resultados e distinguir execução atual de evolução planejada. Documentação e acesso ao produto devem estar a um clique, e o GitHub deve ter destino real e aviso de privacidade visível.

Verifique especialmente o funcionamento em telas pequenas, navegação por teclado, contraste, botões de copiar e destinos dos links. Os exemplos devem refletir a API vigente. A apresentação de open source, execução distribuída e recursos em piloto deve manter os estados descritos neste documento até que o produto avance.

O filme deve avançar ao descer, recuar ao subir e permanecer estável ao parar. Cada cena precisa de entrada, transformação, quadro de leitura e saída reconhecíveis. Teste a continuidade nas duas direções e a correspondência entre texto e imagem. A experiência estática, a composição vertical e a falha de carregamento da mídia fazem parte dos critérios de entrega.

## Referências do produto

- [Documentação pública](https://dev.ingestify.ai/docs).
- [Conversão de documentos](features/conversion.md).
- [Visão e OCR](features/vision.md).
- [Motores de execução](features/engines.md).
- [Armazenamento e retenção](features/storage-and-retention.md).
- [Transcrição ao vivo](features/live-transcription.md).
- [Organização em projetos](features/projects.md).
- [Repositório no GitHub](https://github.com/geda-valentim/ingestify-to-ai), público, conferido durante a produção.
