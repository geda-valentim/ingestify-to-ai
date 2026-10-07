import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Building2,
  Check,
  Database,
  FileText,
  FolderTree,
  Image as ImageIcon,
  Layers,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { GITHUB } from "@/components/landing/content";
import { DOCS_ORIGIN } from "../docs/config";
import styles from "./business.module.css";

export const dynamic = "error";
export const metadata: Metadata = {
  title: "Ingestify for Business — Dados prontos para sua aplicação de IA",
  description:
    "Converta documentos, imagens e gravações em conteúdo para sua aplicação. Organize por projeto e acompanhe jobs. Análises de imagens Full e faces podem entregar resultados em S3, MinIO, Google Cloud Storage e Azure Blob Storage.",
  alternates: { canonical: `${DOCS_ORIGIN}/business` },
  openGraph: {
    title: "Ingestify for Business",
    description:
      "Do arquivo ao dado organizado. Uma plataforma de processamento para integradores, produtos de IA e equipes de dados.",
    url: `${DOCS_ORIGIN}/business`,
    type: "website",
    locale: "pt_BR",
  },
};

const audiences = [
  {
    number: "01",
    title: "Agências e integradores",
    body: "Reutilize o fluxo de processamento nos projetos que você entrega. Organize os trabalhos de cada cliente e conecte os resultados à sua aplicação.",
    example: "Prepare documentos e gravações para as aplicações dos seus clientes.",
  },
  {
    number: "02",
    title: "Produtos e agentes de IA",
    body: "Conecte sua aplicação à API para receber arquivos, acompanhar jobs e consultar texto e metadados quando estiverem prontos.",
    example: "Dê ao seu agente acesso ao conteúdo de um PDF, uma imagem ou uma conversa.",
  },
  {
    number: "03",
    title: "Equipes de dados e automação",
    body: "Transforme arquivos dispersos em resultados que sua equipe consegue consultar e utilizar pela API. Para imagens Full e faces, configure a entrega no seu armazenamento.",
    example: "Prepare dados para consultas, automações e análises na sua infraestrutura.",
  },
];

const capabilities = [
  {
    icon: FileText,
    label: "DOCUMENTOS",
    title: "O conteúdo ganha estrutura.",
    body: "Converta documentos em Markdown e metadados. Acompanhe PDFs por página e consulte os resultados disponíveis.",
    href: "/pt/docs/documents",
    link: "Conversão de documentos",
  },
  {
    icon: AudioLines,
    label: "ÁUDIO E VÍDEO",
    title: "A conversa vira dado.",
    body: "Envie gravações pela API e obtenha transcrições com marcações de tempo. Capture o microfone na interface e consulte os resultados na plataforma.",
    href: "/pt/docs/transcription",
    link: "Transcrição de gravações",
  },
  {
    icon: ImageIcon,
    label: "IMAGENS",
    title: "Mais contexto em cada imagem.",
    body: "Extraia texto, descrições e regiões. Use Full Analysis para explorar as análises disponíveis e acompanhar cada etapa.",
    href: "/pt/docs/platform-images",
    link: "Usar imagens e Full Analysis",
  },
];

const questions = [
  {
    title: "Preciso integrar pela API para começar?",
    answer: "Comece com documentos e imagens pela interface, ou capture áudio do microfone na tela Live. O envio de arquivos de áudio e vídeo está disponível pela API. Você acompanha os jobs e consulta os resultados na plataforma. O acesso depende das permissões da sua conta e da configuração da instalação.",
    href: "/pt/docs/platform-start",
    link: "Começar pela plataforma",
  },
  {
    title: "Onde os resultados são entregues?",
    answer: "Você consulta documentos, transcrições e análises de imagem pela plataforma e pela API. A entrega automática em Amazon S3, MinIO, Google Cloud Storage e Azure Blob Storage está conectada às análises de imagem Full e faces. Nesses modos, configure o bucket ou container, o particionamento e as credenciais do destino. Sua aplicação pode recuperar e armazenar os resultados das demais operações pela API.",
    href: "/pt/docs/platform-datalakes",
    link: "Configurar o armazenamento",
  },
  {
    title: "Consigo analisar todas as conversas de um cliente?",
    answer: "Organize os jobs de transcrição por projeto e pasta. Sua aplicação recupera os transcripts pela API, associa cada conversa ao cliente e armazena os dados para agregação. A análise consolidada das conversas é realizada pela sua aplicação ou ferramenta de análise. O particionamento customer_id e a entrega automática JSONL estão disponíveis para as análises de imagem Full e faces.",
    href: "/pt/docs/platform-transcription",
    link: "Usar transcrições",
  },
  {
    title: "Posso operar na minha infraestrutura?",
    answer: "O repositório oferece implantação com Docker Compose e workers locais. Escolha as engines e os destinos de armazenamento adequados ao seu ambiente. O caminho dos dados depende dos provedores e das rotas que você habilita.",
    href: "/pt/docs/compute",
    link: "Conhecer as opções de processamento",
  },
];

function Pipeline() {
  return (
    <figure className={styles.pipeline} aria-labelledby="pipeline-caption">
      <div className={styles.pipelineHeading}>
        <span>UM FLUXO DE DADOS</span>
        <span className={styles.exampleBadge}>Exemplo ilustrativo</span>
      </div>
      <div className={styles.sources}>
        <div><FileText size={19} aria-hidden="true" /><span>contrato.pdf</span></div>
        <div><AudioLines size={19} aria-hidden="true" /><span>conversa.mp3</span></div>
        <div><ImageIcon size={19} aria-hidden="true" /><span>imagem.png</span></div>
      </div>
      <div className={styles.connector} aria-hidden="true"><ArrowDown size={21} /></div>
      <div className={styles.processor}>
        <div><Layers size={23} aria-hidden="true" /><strong>Ingestify</strong><span>Interface + API</span></div>
        <ol>
          <li><span>01</span> Receber e organizar</li>
          <li><span>02</span> Processar e acompanhar</li>
          <li><span>03</span> Disponibilizar o resultado</li>
        </ol>
      </div>
      <div className={styles.connector} aria-hidden="true"><ArrowDown size={21} /></div>
      <div className={styles.output}>
        <Database size={24} aria-hidden="true" />
        <div><strong>Resultado na plataforma e API</strong><p>Texto · metadados · análises</p></div>
        <Check size={17} aria-hidden="true" />
      </div>
      <figcaption id="pipeline-caption">Sua aplicação consulta o resultado. Imagens Full e faces também oferecem entrega automática no armazenamento configurado.</figcaption>
    </figure>
  );
}

export default function BusinessPage() {
  return (
    <div className={styles.page} lang="pt-BR">
      <a href="#business-content" className={styles.skip}>Ir para o conteúdo</a>
      <header className={styles.header}>
        <Link href="/" aria-label="Página inicial do Ingestify"><Brand /></Link>
        <nav aria-label="Navegação principal">
          <Link href="/agents" className={styles.desktopLink}>Para agentes</Link>
          <Link href="/business" className={styles.desktopLink} aria-current="page">Business</Link>
          <Link href="/pt/docs">Docs</Link>
          <Link href="/convert" className={styles.smallButton}>Começar <ArrowUpRight size={14} aria-hidden="true" /></Link>
        </nav>
      </header>
      <main id="business-content">
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>INGESTIFY FOR BUSINESS</p>
            <h1>Do arquivo.<br />Ao dado.<br /><span>Ao seu produto.</span></h1>
            <p className={styles.heroDescription}>Documentos, imagens e conversas em um fluxo de processamento. Dados organizados para a aplicação de IA que você está construindo.</p>
            <div className={styles.actions}>
              <Link href="/convert" className={styles.button}>Processar um arquivo <ArrowUpRight size={17} aria-hidden="true" /></Link>
              <a href="#para-quem" className={styles.textLink}>Explore os usos <ArrowDown size={16} aria-hidden="true" /></a>
            </div>
            <p className={styles.heroNote}>Documentos e imagens na interface. Gravações pela API. Microfone na tela Live.</p>
          </div>
          <Pipeline />
        </section>

        <div className={styles.providerRail} aria-label="Destinos de armazenamento para análises de imagem Full e faces">
          <span>ENTREGA AUTOMÁTICA · IMAGENS FULL E FACES</span>
          <strong>Amazon S3</strong><strong>MinIO</strong><strong>Google Cloud Storage</strong><strong>Azure Blob Storage</strong>
        </div>

        <section className={styles.section} id="para-quem">
          <div className={styles.sectionLabel}><span>01 / PARA QUEM CONSTRÓI</span><span>UM FLUXO. DIFERENTES APLICAÇÕES.</span></div>
          <div className={styles.sectionIntro}>
            <h2>Seu trabalho começa<br /><span>com dados melhores.</span></h2>
            <p>Receber um arquivo é só o começo. Prepare o conteúdo, acompanhe o processamento e conecte o resultado ao que sua equipe entrega.</p>
          </div>
          <div className={styles.audiences}>
            {audiences.map((audience) => <article key={audience.number}>
              <span>{audience.number}</span><h3>{audience.title}</h3>
              <div><p>{audience.body}</p><p className={styles.audienceExample}>{audience.example}</p></div>
              <ArrowUpRight size={22} aria-hidden="true" />
            </article>)}
          </div>
        </section>

        <section className={`${styles.section} ${styles.dark}`} id="processamento">
          <div className={styles.sectionLabel}><span>02 / O QUE VOCÊ PODE PROCESSAR</span><span>CONTEÚDO QUE SUA APLICAÇÃO CONSEGUE USAR</span></div>
          <h2>Cada formato.<br /><span>Um próximo passo.</span></h2>
          <div className={styles.capabilities}>
            {capabilities.map(({ icon: Icon, ...item }) => <article key={item.label}>
              <Icon size={32} strokeWidth={1.5} aria-hidden="true" />
              <span>{item.label}</span><h3>{item.title}</h3><p>{item.body}</p>
              <Link href={item.href} className={styles.textLink}>{item.link}<ArrowUpRight size={16} aria-hidden="true" /></Link>
            </article>)}
          </div>
        </section>

        <section className={styles.section} id="resultados-por-cliente">
          <div className={styles.sectionLabel}><span>03 / UM CLIENTE, VÁRIOS RESULTADOS</span><span>IMAGENS FULL E FACES · ENTREGA PARTICIONADA</span></div>
          <div className={styles.customerGrid}>
            <div>
              <h2>Organize por cliente.<br /><span>Prepare sua análise.</span></h2>
              <p className={styles.sectionDescription}>Uma foto de atendimento hoje. Outra na semana que vem. Em análises de imagem Full e faces, use um identificador como <code>customer_id</code> para organizar os resultados do mesmo cliente no seu armazenamento.</p>
              <ul className={styles.checklist}>
                <li><Check size={17} aria-hidden="true" />Defina a estratégia pela interface ou pela API.</li>
                <li><Check size={17} aria-hidden="true" />Envie o identificador no destino da análise Full ou faces.</li>
                <li><Check size={17} aria-hidden="true" />Combine cliente, projeto e data no particionamento.</li>
                <li><Check size={17} aria-hidden="true" />Habilite JSONL para preparar datasets consultáveis.</li>
              </ul>
              <Link href="/pt/docs/platform-partitioning" className={styles.textLink}>Veja como configurar <ArrowUpRight size={16} aria-hidden="true" /></Link>
            </div>
            <figure className={styles.customerExample}>
              <figcaption><FolderTree size={18} aria-hidden="true" /><span>EXEMPLO · CLIENTE ACME-042</span></figcaption>
              <div className={styles.conversations}>
                <div><ImageIcon size={18} aria-hidden="true" /><span>foto-atendimento-01.jpg</span><small>Full Analysis · customer_id = acme-042</small></div>
                <div><ImageIcon size={18} aria-hidden="true" /><span>foto-atendimento-02.jpg</span><small>Full Analysis · customer_id = acme-042</small></div>
              </div>
              <div className={styles.datasetTitle}><Database size={17} aria-hidden="true" /><strong>Dataset organizado</strong><span>JSONL</span></div>
              <pre aria-label="Exemplo simplificado de caminho particionado">{"datasets/\n  layout-…/\n    customer_id=acme-042/\n      year=2026/\n        month=10/\n          day=07/\n            <job_id>.jsonl"}</pre>
              <p>Exemplo simplificado de layout de imagens Full. Cada job entrega seu registro; sua aplicação consulta os dados e executa a análise conjunta dos resultados.</p>
            </figure>
          </div>
        </section>

        <section className={`${styles.section} ${styles.soft}`} id="operacao">
          <div className={styles.sectionLabel}><span>04 / DA PRIMEIRA CONVERSÃO À INTEGRAÇÃO</span><span>VISIBILIDADE PARA QUEM OPERA</span></div>
          <div className={styles.sectionIntro}><h2>Comece na tela.<br /><span>Conecte ao seu fluxo.</span></h2><p>Valide o resultado com arquivos reais e incorpore o processamento à sua aplicação quando fizer sentido.</p></div>
          <div className={styles.operationGrid}>
            <article><Building2 size={27} aria-hidden="true" /><h3>Use a plataforma</h3><p>Crie projetos, envie documentos e imagens, acompanhe o andamento e visualize resultados. Em imagens Full e faces, selecione uma conexão de armazenamento para entrega automática.</p><Link href="/pt/docs/platform-start" className={styles.textLink}>Guia de uso <ArrowUpRight size={16} aria-hidden="true" /></Link></article>
            <article><Layers size={27} aria-hidden="true" /><h3>Integre pela API</h3><p>Autentique sua aplicação, envie fontes e guarde o job ID. Passe o contexto de projeto, consulte o status e recupere os resultados. Sua aplicação pode armazenar transcripts e outros resultados no destino que utiliza.</p><Link href="/docs" className={styles.textLink}>Documentação da API <ArrowUpRight size={16} aria-hidden="true" /></Link></article>
          </div>
          <div className={styles.operatingNotes}><p><strong>Organização.</strong> Projetos, pastas e tags ajudam a encontrar o que foi processado.</p><p><strong>Acompanhamento.</strong> Jobs mostram andamento, resultados e falhas para orientar a recuperação.</p><p><strong>Infraestrutura.</strong> Configure engines e destinos conforme o seu ambiente de operação.</p></div>
        </section>

        <section className={styles.section} id="duvidas">
          <div className={styles.sectionLabel}><span>05 / ANTES DE COMEÇAR</span><span>DO USO À OPERAÇÃO</span></div>
          <div className={styles.faqGrid}><h2>Questões<br /><span>práticas.</span></h2><div>{questions.map((question) => <details key={question.title}><summary>{question.title}<span aria-hidden="true">+</span></summary><p>{question.answer}</p><Link href={question.href} className={styles.textLink}>{question.link}<ArrowUpRight size={15} aria-hidden="true" /></Link></details>)}</div></div>
        </section>

        <section className={styles.closing}>
          <p className={styles.eyebrow}>SEU PRÓXIMO PASSO</p>
          <h2>Traga um arquivo real.<br /><span>Veja onde ele pode chegar.</span></h2>
          <p>Comece por um caso de uso da sua equipe. Valide o conteúdo e construa a integração a partir do resultado.</p>
          <div className={styles.actions}><Link href="/convert" className={styles.button}>Abrir a plataforma <ArrowRight size={17} aria-hidden="true" /></Link><Link href="/agents" className={styles.textLink}>Ingestify para agentes <ArrowUpRight size={16} aria-hidden="true" /></Link></div>
        </section>
      </main>
      <footer className={styles.footer}>
        <Link href="/" aria-label="Página inicial do Ingestify"><Brand /></Link>
        <p>Data Engineering + AI-ready conversion.</p>
        <nav aria-label="Links do rodapé"><Link href="/agents">Para agentes</Link><Link href="/pt/docs">Docs</Link><a href={GITHUB}>GitHub</a></nav>
      </footer>
    </div>
  );
}
