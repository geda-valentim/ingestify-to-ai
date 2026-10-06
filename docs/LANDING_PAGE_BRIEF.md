# Direção de conteúdo e design da home do Ingestify

O Ingestify transforma documentos, imagens, áudio e vídeo em informação utilizável por aplicações de IA. A home deve tornar essa proposta visível em poucos segundos, mostrar as operações disponíveis e explicar o controle sobre sua execução. A ambição é evoluir para uma plataforma open source de operações de transformação, executadas localmente ou de forma distribuída.

Este documento orienta o conteúdo, o design e a implementação da landing page. Os textos públicos propostos aparecem em blocos de citação; as orientações de composição e comportamento acompanham cada seção. O estado das funcionalidades corresponde à documentação consultada em 5 de outubro de 2026. A abertura do código está planejada e o repositório permanece privado.

## Posicionamento

**Definição do produto**

> Uma plataforma para transformar documentos, imagens, áudio e vídeo em dados para IA, com controle sobre o processamento e os resultados.

**Promessa central**

> Seus arquivos se tornam informação que suas aplicações podem usar.

O público inicial são desenvolvedores, equipes de produto e pessoas que automatizam rotinas com IA. Eles precisam extrair informação de arquivos, integrar o processamento a outros sistemas e entender onde cada trabalho está rodando.

A home deve responder, nesta ordem: o que posso transformar, o que recebo, como uso e onde posso executar. A proposta open source fecha essa narrativa com a direção de evolução e um caminho claro para o GitHub.

A linguagem deve ser direta e concreta. Use “transcrever uma gravação”, “extrair texto de uma imagem” e “converter um PDF”. Termos como workers, modelos e roteamento entram quando ajudam a explicar uma escolha. A página deve transmitir utilidade, cuidado com a informação e clareza operacional.

## Direção visual

A referência estética é uma bancada digital de processamento: arquivos entram, uma operação é executada e o resultado aparece organizado. O próprio produto fornece os elementos visuais da página.

Use fundo escuro em grafite, superfícies discretamente mais claras e texto em branco suave. Verde deve identificar ações principais e trabalhos concluídos; azul pode distinguir execução remota. Reserve âmbar para recursos em piloto. Valide o contraste de todos os textos e controles na implementação.

A tipografia principal deve ter boa leitura e títulos amplos, com pesos bem definidos. Use uma fonte monoespaçada apenas para nomes de arquivos, trechos de código, formatos e eventos de processamento. O espaçamento generoso e a hierarquia devem sustentar a composição.

O elemento de maior destaque será uma prévia de transformação. Mostre um arquivo com conteúdo legível de um lado e seu resultado do outro. Uma trilha curta entre os dois indica a operação. Nas seções seguintes, alterne essa linguagem visual com uma composição de execução e uma área de integração por API.

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

> Construindo o caminho para open source. Repositório privado por enquanto.

No desktop, distribua texto e demonstração em duas colunas, com mais espaço para o resultado visual. No celular, apresente primeiro a promessa e os botões, seguidos pela demonstração.

### Demonstração de transformação

Apresente três abas: “Documento”, “Áudio” e “Imagem”. Cada uma troca a entrada, a operação e o resultado exibidos.

| Aba | Entrada ilustrativa | Operação | Resultado ilustrativo |
|---|---|---|---|
| Documento | `relatorio.pdf`, com título, parágrafo e tabela | Conversão de documento | Trecho em Markdown preservando esses elementos. |
| Áudio | `reuniao.mp3`, com uma forma de onda | Transcrição | Duas falas com timestamps e opções TXT, JSON e VTT. |
| Imagem | `recibo.png`, com valores legíveis | OCR | Texto extraído e regiões destacadas na imagem. |

O visitante deve conseguir comparar a origem e a saída. Todo o conteúdo deve ser sintético e identificado como “Exemplo ilustrativo”. A demonstração deve funcionar sem conta e sem disparar inferência real. Ela não deve exibir controles de upload que aparentem enviar arquivos.

Uma transição curta pode revelar o resultado ao trocar de aba. O conteúdo final precisa permanecer disponível com animações reduzidas. Não use durações, custos ou percentuais de precisão fictícios.

## Operações disponíveis

Âncora sugerida: `operacoes`.

**Título**

> Operações que fazem parte do seu dia a dia.

**Introdução**

> Prepare documentos para uma base de conhecimento, transforme gravações em texto e extraia informação de imagens. Escolha a operação e use o resultado no seu próximo passo.

Use três blocos com exemplos de saída. Dê ao bloco de documentos mais espaço visual e componha os demais ao lado ou abaixo.

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

Em uma faixa menor, após as operações principais:

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

Apresente uma composição com uma fila de trabalhos ao centro e dois destinos: “Workers locais” e “Modal para transcrição”. Identifique documentos, imagens e áudio no destino local; no destino Modal, apenas áudio.

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

Mostre uma prévia compacta da interface, com projeto, arquivo, operação e status. Priorize uma captura real preparada com dados de demonstração. Caso seja um mockup, identifique-o como ilustrativo e limite-o a comportamentos existentes.

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

Apresente um exemplo curto de envio de documento, com botão de copiar:

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
> Estamos preparando a abertura do código. O repositório ainda é privado; a direção é permitir que mais pessoas inspecionem o funcionamento, contribuam com operações e adaptem a plataforma às suas rotinas.

Use uma composição simples com dois grupos claramente nomeados, sem datas de entrega:

| Disponível hoje | Direção de evolução |
|---|---|
| Conversão de documentos, transcrição e operações de imagem. | Contrato comum para adicionar e versionar operações. |
| Workers locais e transcrição remota via Modal. | Conexão mais simples de outras máquinas e execução distribuída. |
| Projetos, jobs, API e controles de execução. | Composição de operações em fluxos reutilizáveis. |

### Link do GitHub

Destino confirmado pelo remote do projeto: [github.com/geda-valentim/ingestify-to-ai](https://github.com/geda-valentim/ingestify-to-ai).

**Texto do link**

> GitHub · Repositório privado

**Aviso visível ao lado do link**

> A abertura pública está planejada. Enquanto o repositório estiver privado, o GitHub pode mostrar uma página 404 para quem não tem acesso.

O link deve permanecer clicável, com o estado indicado em texto, inclusive para leitores de tela. Não use um botão desabilitado ou esconda a condição apenas em tooltip. O clique abre o destino real e não promete inscrição ou notificação futura.

Quando o código se tornar público, atualizar o rótulo para “Ver no GitHub”, remover o aviso e adicionar instruções reais de contribuição e instalação. Essa mudança depende da abertura efetiva do repositório.

## Perguntas frequentes

**O Ingestify já é open source?**

> A abertura do código está planejada. Por enquanto, o repositório no GitHub é privado.

**Posso executar no meu ambiente?**

> A arquitetura suporta workers locais em CPU e GPU. Enquanto o repositório estiver privado, a instalação a partir do código depende de acesso ao projeto. Os requisitos variam conforme a operação e os modelos utilizados.

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

O rodapé reúne marca, documentação, referência da API, acesso à plataforma e GitHub com o indicador de repositório privado. O cadastro não deve ser uma chamada fixa, pois depende da configuração de registro do ambiente.

## Comportamento e adaptação

No celular, as seções seguem a mesma narrativa, com exemplos em uma coluna e nenhum texto essencial oculto. Blocos de código podem ter rolagem horizontal própria; o restante da página deve caber na tela.

As abas da demonstração e as perguntas frequentes devem funcionar por teclado, com foco visível. Estados como “Piloto” e “Privado” precisam de rótulos textuais. Respeite a preferência por movimento reduzido e mantenha o conteúdo utilizável sem animação.

Use animações curtas para troca de exemplos e revelação dos resultados. Evite vídeo pesado no carregamento inicial e efeitos que disputem atenção com o conteúdo. A página deve abrir sem chamadas de inferência, autenticação ou acesso ao GitHub.

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

## Referências do produto

- [Documentação pública](https://dev.ingestify.ai/docs).
- [Conversão de documentos](features/conversion.md).
- [Visão e OCR](features/vision.md).
- [Motores de execução](features/engines.md).
- [Armazenamento e retenção](features/storage-and-retention.md).
- [Transcrição ao vivo](features/live-transcription.md).
- [Organização em projetos](features/projects.md).
- [Repositório no GitHub](https://github.com/geda-valentim/ingestify-to-ai), privado nesta etapa.
