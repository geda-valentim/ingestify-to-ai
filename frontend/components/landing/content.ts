export const GITHUB = "https://github.com/geda-valentim/ingestify-to-ai";
export const chapters = [
  {
    name: "Arquivos",
    eyebrow: "INFORMAÇÃO EM MOVIMENTO",
    title: "Seus arquivos. Prontos para IA.",
    body: "Documentos, imagens, áudio e vídeo se transformam em informação que suas aplicações podem usar.",
    action: "Explorar a plataforma",
    href: "/login",
    note: "",
  },
  {
    name: "Documentos",
    eyebrow: "01 / DOCUMENTOS",
    title: "Do documento ao Markdown.",
    body: "Texto, tabelas e estrutura. Converta documentos e acompanhe o processamento de cada página.",
    action: "Conversão de documentos",
    href: "/docs#documentos",
    note: "",
  },
  {
    name: "Áudio",
    eyebrow: "02 / ÁUDIO E VÍDEO",
    title: "Da gravação ao texto.",
    body: "Transcrições com timestamps e legendas para levar a conversa ao próximo passo.",
    note: "Em vídeos, processamos a faixa de áudio.",
    action: "Explorar transcrição",
    href: "/docs#transcribe",
  },
  {
    name: "Imagens",
    eyebrow: "03 / VISÃO",
    title: "A informação dentro da imagem.",
    body: "Extraia texto e suas regiões com OCR. Gere descrições de imagens pela API.",
    action: "Operações de imagem",
    href: "/docs#imagens",
    note: "",
  },
  {
    name: "Execução",
    eyebrow: "04 / CONTROLE",
    title: "Escolha onde acontece.",
    body: "Workers locais e transcrição no Modal. Defina a execução conforme capacidade, prioridade e orçamento.",
    note: "O destino dos dados também depende do provider escolhido.",
    action: "Entender a execução",
    href: "/docs#compute",
  },
  {
    name: "Integração",
    eyebrow: "05 / SUA ROTINA",
    title: "Um trabalho. Muitas conexões.",
    body: "Organize resultados por projeto e tags. Conecte as operações à sua aplicação por API.",
    action: "Ver exemplo da API",
    href: "#api",
    note: "",
  },
  {
    name: "Evolução",
    eyebrow: "06 / VISÃO DE EVOLUÇÃO",
    title: "Começa local. Pode ir além.",
    body: "Nossa direção: conectar outras máquinas e compor operações reutilizáveis em uma plataforma aberta.",
    note: "A distribuição geral e a composição de operações são planos de evolução.",
    action: "Acompanhar no GitHub",
    href: GITHUB,
  },
  {
    name: "Começar",
    eyebrow: "CONSTRUA O PRÓXIMO PASSO",
    title: "Da informação à sua próxima ideia.",
    body: "Conheça o projeto, explore os contratos da API e transforme sua rotina com o Ingestify.",
    action: "Ler a documentação",
    href: "/docs",
    note: "",
  },
];
export const example = [
  'curl -X POST "https://dev.ingestify.ai/api/upload" \\',
  '  -H "X-API-Key: SUA_CHAVE" \\',
  '  -F "file=@relatorio.pdf" \\',
  '  -F "project=Documentos" \\',
  '  -F "docling_preset=quality"',
].join("\n");
export const faq = [
  [
    "O que posso transformar?",
    "Documentos em Markdown, gravações em transcrições e legendas, e imagens em texto por OCR ou descrições pela API. Consulte os formatos e limites de cada operação nos docs.",
  ],
  [
    "Tudo pode rodar localmente?",
    "A plataforma tem workers locais. O processamento e o destino dos dados dependem também do engine e do provider configurados. Providers externos podem enviar conteúdo a outros serviços; confira sua configuração antes de usar arquivos sensíveis.",
  ],
  [
    "Como funciona a execução na nuvem?",
    "A integração com o Modal atende à transcrição, conforme as regras de capacidade, prioridade e orçamento configuradas. A distribuição geral entre máquinas e a composição de operações fazem parte da visão de evolução.",
  ],
  [
    "O Ingestify analisa as cenas de um vídeo?",
    "Na transcrição, o vídeo é uma fonte de áudio. O resultado descreve a fala; essa operação não analisa as cenas visuais.",
  ],
  [
    "Posso integrar com minha aplicação?",
    "Sim. Crie uma API key na plataforma e consulte os contratos nos docs. Documentos e transcrições usam jobs; operações de imagem podem devolver o resultado na própria requisição.",
  ],
  [
    "Onde acompanho o código e a evolução?",
    "O repositório está disponível no GitHub. A proposta é evoluir com a comunidade; consulte os arquivos do projeto para conhecer o estado de cada recurso e as condições de uso.",
  ],
];
