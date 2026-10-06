"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowDown, ArrowRight, ArrowUpRight, Check, Copy, FileText, Github, Image as ImageIcon, Layers, Monitor, Radio, Terminal } from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { chapterProgress, timelineAt } from "./timeline";
import { chapters, example, faq, GITHUB } from "./content";
import "./landing.css";

function frame(chapter: number, end = false) {
  return `/landing/storyboard/white-rainbow/scene-0${chapter + 1}-${end ? (chapter === 4 ? "end-v2" : "end") : "start"}.png`;
}
function ResultExample({ chapter }: { chapter: number }) {
  if (chapter === 1) return <pre className="landing-result"><span>MARKDOWN · EXEMPLO</span>{"# Relatório\n\n| Item | Valor |\n| --- | --- |\n| Total | 42,00 |"}</pre>;
  if (chapter === 2) return <div className="landing-result"><span>TRANSCRIÇÃO · EXEMPLO</span><p><time>00:00 → 00:03</time> Vamos começar pelo documento.</p><p><time>00:03 → 00:06</time> O resultado entra na aplicação.</p></div>;
  if (chapter === 3) return <div className="landing-result"><span>OCR · EXEMPLO</span><p>TOTAL 42,00</p><small>Texto extraído + regiões na imagem</small></div>;
  return null;
}
export function LandingPage() {
  const story = useRef<HTMLElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const desiredTime = useRef(0);
  const [position, setPosition] = useState(() => timelineAt(0));
  const [staticMode, setStaticMode] = useState(false);
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [mediaReady, setMediaReady] = useState(false);
  const [mediaFailed, setMediaFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const signedIn = useAuthStore(s => s._hasHydrated && !!s.token && !!s.user);
  const current = chapters[position.chapter];

  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    const update = () => setStaticMode(preference.matches || !!connection?.saveData || innerHeight < 620);
    update(); setPreferencesReady(true);
    preference.addEventListener("change", update);
    addEventListener("resize", update);
    return () => { preference.removeEventListener("change", update); removeEventListener("resize", update); };
  }, []);
  const seek = useCallback(() => {
    const media = video.current;
    if (!media || media.readyState < 2 || media.seeking || !Number.isFinite(media.duration)) return;
    const target = Math.min(desiredTime.current, Math.max(0, media.duration - 0.04));
    if (Math.abs(media.currentTime - target) > 0.025) media.currentTime = target;
  }, []);
  useEffect(() => {
    if (staticMode) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const el = story.current;
      if (!el) return;
      const next = timelineAt((72 - el.getBoundingClientRect().top) / Math.max(1, el.offsetHeight - (innerHeight - 72)));
      desiredTime.current = next.time; setPosition(next); seek();
    };
    const schedule = () => { if (!raf) raf = requestAnimationFrame(update); };
    update(); addEventListener("scroll", schedule, { passive: true }); addEventListener("resize", schedule);
    return () => { cancelAnimationFrame(raf); removeEventListener("scroll", schedule); removeEventListener("resize", schedule); };
  }, [staticMode, seek]);
  function goToChapter(index: number) {
    const el = story.current;
    if (!el) return;
    scrollTo({ top: scrollY + el.getBoundingClientRect().top - 72 + chapterProgress(index) * (el.offsetHeight - (innerHeight - 72)), behavior: "auto" });
  }
  async function copyExample() {
    try { await navigator.clipboard.writeText(example); setCopied(true); setCopyFailed(false); }
    catch { setCopyFailed(true); }
  }

  return <div className="landing" lang="pt-BR">
    <a className="landing-skip" href="#operacoes">Pular apresentação</a>
    <header className="landing-header">
      <Link className="landing-brand" href="/" aria-label="Ingestify, início"><span className="landing-mark" aria-hidden="true"><Layers size={20} strokeWidth={1.5} /></span>ingestify<span className="landing-brand-dot">.</span></Link>
      <nav aria-label="Navegação principal"><a href="#operacoes">Plataforma</a><Link href="/docs">Docs</Link><a href={GITHUB} className="landing-github" aria-label="Ingestify no GitHub"><Github size={18} /></a><Link className="landing-button small" href={signedIn ? "/dashboard" : "/login"}>{signedIn ? "Abrir painel" : "Entrar"}<ArrowUpRight size={14} /></Link></nav>
    </header>
    <main>
      <h1 className="sr-only">Seus arquivos. Prontos para IA.</h1>
      <noscript><style>{`.landing-story{height:calc(100svh - 72px)}.landing-story-bottom nav{display:none}`}</style></noscript>
      {!staticMode ? <section className="landing-story" ref={story} aria-label="Explore o Ingestify pela rolagem">
        <div className="landing-stage">
          <div className="landing-film" aria-hidden="true">
            {/* Full frame preserves both sides of the transformation on mobile. */}
            <Image src={frame(mediaReady ? 0 : position.chapter, !mediaReady && position.result)} alt="" width={1672} height={941} sizes="100vw" priority />
            {preferencesReady && !mediaFailed && <video ref={video} src="/landing/film/ingestify-scroll.mp4" muted playsInline preload="auto" tabIndex={-1} className={mediaReady ? "is-ready" : ""} onLoadedData={() => { setMediaReady(true); seek(); }} onSeeked={seek} onError={() => { setMediaFailed(true); setMediaReady(false); }} />}
          </div>
          <div className={`landing-story-copy ${position.bridge ? "is-bridge" : ""} ${position.result && position.chapter >= 1 && position.chapter <= 3 ? "has-result" : ""}`} data-chapter={position.chapter}>
            <p className="landing-eyebrow">{position.future ? "VISÃO DE EVOLUÇÃO" : current.eyebrow}</p>
            <h2>{current.title}</h2>
            {!position.bridge && <><p className="landing-story-description">{current.body}</p><a className="landing-text-link" href={current.href}>{current.action}<ArrowUpRight size={16} /></a>{current.note && <p className="landing-note">{current.note}</p>}{position.result && <ResultExample chapter={position.chapter} />}</>}
          </div>
          <div className="landing-story-bottom"><span className="landing-scroll-hint"><ArrowDown size={14} /> Role para explorar</span><nav aria-label="Capítulos da apresentação">{chapters.map((c, i) => <button key={c.name} onClick={() => goToChapter(i)} aria-label={`Cena ${i + 1}: ${c.name}`} aria-current={position.chapter === i ? "step" : undefined}><span>{String(i + 1).padStart(2, "0")}</span><span className="chapter-name">{c.name}</span></button>)}</nav><a href="#operacoes">Pular <ArrowDown size={13} /></a></div>
          <span className="landing-film-caption">Demonstração ilustrativa</span>
        </div>
      </section> : <section className="landing-static" aria-label="Conheça o Ingestify">{chapters.map((c, i) => <article key={c.name}><div><p className="landing-eyebrow">{c.eyebrow}</p><h2>{c.title}</h2><p>{c.body}</p>{c.note && <p className="landing-note">{c.note}</p>}<a className="landing-text-link" href={c.href}>{c.action}<ArrowUpRight size={16} /></a><ResultExample chapter={i} /></div><Image width={1672} height={941} sizes="(max-width:767px) 100vw, 65vw" src={frame(i, true)} alt={`Ilustração: ${c.title}`} loading={i ? "lazy" : "eager"} /></article>)}</section>}

      <section id="operacoes" className="landing-section landing-operations">
        <div className="landing-section-heading"><p className="landing-eyebrow">OS FORMATOS MUDAM. O FLUXO CONTINUA.</p><h2>Uma entrada.<br />Novas possibilidades.</h2><p>Escolha a operação. Obtenha um resultado que pode seguir direto para o seu próximo processo.</p></div>
        <div className="landing-operation-grid">
          <article><FileText size={25} strokeWidth={1.3} /><p className="landing-card-kicker">DOCUMENTOS → MARKDOWN</p><h3>Estrutura que segue com você.</h3><p>Converta documentos, preserve o conteúdo em Markdown e acompanhe PDFs por página.</p><ResultExample chapter={1} /><Link className="landing-text-link" href="/docs#documentos">Documentos<ArrowUpRight size={15} /></Link></article>
          <article><Radio size={25} strokeWidth={1.3} /><p className="landing-card-kicker">ÁUDIO E VÍDEO → TEXTO</p><h3>Conversas viram conteúdo.</h3><p>Transcrição, timestamps e legendas. Em vídeos, a operação utiliza a faixa de áudio.</p><ResultExample chapter={2} /><aside className="landing-live-pilot"><strong>Microfone ao vivo · Piloto</strong><p>Requer ativação pelo operador e capacidade GPU.</p><Link className="landing-text-link" href="/docs#microfone-live">Conhecer o piloto<ArrowUpRight size={13} /></Link></aside><Link className="landing-text-link" href="/docs#transcribe">Transcrição<ArrowUpRight size={15} /></Link></article>
          <article><ImageIcon size={25} strokeWidth={1.3} /><p className="landing-card-kicker">IMAGENS → INFORMAÇÃO</p><h3>Encontre o texto na imagem.</h3><p>OCR com texto e regiões. A API também oferece descrição de imagens para outros fluxos.</p><ResultExample chapter={3} /><Link className="landing-text-link" href="/docs#imagens">Imagens<ArrowUpRight size={15} /></Link></article>
        </div><p className="landing-note">Exemplos ilustrativos. Formatos e resultados dependem da operação, do arquivo e do provider.</p>
      </section>

      <section className="landing-section landing-compute" id="execucao"><div><p className="landing-eyebrow">SUA INFRAESTRUTURA. SUAS ESCOLHAS.</p><h2>O controle também<br />faz parte do resultado.</h2><p>Execute na infraestrutura que você configura. Acompanhe o trabalho, organize os resultados e escolha os recursos para cada rotina.</p><Link className="landing-text-link" href="/docs#compute">Conhecer a execução<ArrowUpRight size={16} /></Link></div><div className="landing-compute-list"><article><Monitor size={22} /><div><span>DISPONÍVEL</span><h3>Workers locais</h3><p>Documentos e imagens no ambiente configurado. Transcrição local conforme o engine escolhido.</p></div></article><article><Radio size={22} /><div><span>DISPONÍVEL · TRANSCRIÇÃO</span><h3>Capacidade no Modal</h3><p>Destino remoto opcional para áudio, sujeito à configuração de capacidade e orçamento.</p></div></article><article><Layers size={22} /><div><span>VISÃO DE EVOLUÇÃO</span><h3>Mais máquinas. Operações conectadas.</h3><p>Distribuição geral do processamento e composição de operações são a direção de evolução do projeto.</p></div></article></div></section>

      <section className="landing-section landing-api" id="api"><div><p className="landing-eyebrow">FEITO PARA SE CONECTAR</p><h2>Uma operação.<br />Dentro da sua aplicação.</h2><p>Envie um documento, acompanhe o job e obtenha o resultado. Use sua API key para integrar o Ingestify aos seus scripts e serviços.</p><ol className="landing-api-steps"><li><span>01</span>Enviar arquivo</li><li><span>02</span>Acompanhar o job</li><li><span>03</span>Obter o resultado</li></ol><Link className="landing-text-link" href="/docs">Ler a documentação<ArrowUpRight size={16} /></Link></div><div className="landing-code"><div className="landing-code-bar"><span><Terminal size={15} /> Enviar documento</span><button onClick={copyExample} aria-label="Copiar exemplo de envio">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copiado" : "Copiar"}</button></div><pre><code>{example}</code></pre><p>Ambiente de desenvolvimento. Requer uma conta e API key válidas.</p><p role="status">{copyFailed ? "Selecione o código acima para copiar." : copied ? "Exemplo copiado." : ""}</p><a href="/api/docs">Referência da API<ArrowUpRight size={14} /></a></div></section>

      <section className="landing-section landing-community" id="codigo-aberto"><div className="landing-rainbow-line" /><p className="landing-eyebrow">UM PROJETO EM CONSTRUÇÃO ABERTA</p><h2>As próximas operações<br />podem começar com você.</h2><p>Nossa visão é uma plataforma open source para as transformações de IA do dia a dia. Explore o código, acompanhe a evolução e participe da conversa.</p><a href={GITHUB} className="landing-button"><Github size={18} />Ver no GitHub<ArrowUpRight size={16} /></a></section>
      <section className="landing-section landing-faq" id="perguntas"><div><p className="landing-eyebrow">ANTES DO PRIMEIRO ARQUIVO</p><h2>Algumas respostas.</h2></div><div>{faq.map(([q, a]) => <details key={q}><summary>{q}<span aria-hidden="true">+</span></summary><p>{a}</p></details>)}</div></section>
      <section className="landing-section landing-final"><p className="landing-eyebrow">SEU PRÓXIMO FLUXO COMEÇA AQUI</p><h2>O arquivo é só o começo.</h2><div><Link className="landing-button" href={signedIn ? "/dashboard" : "/login"}>Explorar a plataforma<ArrowRight size={17} /></Link><Link className="landing-text-link" href="/docs">Ler os docs<ArrowUpRight size={16} /></Link></div></section>
    </main>
    <footer className="landing-footer"><a href="#" className="landing-brand">ingestify.</a><p>Arquivos em informação. Informação em possibilidades.</p><nav aria-label="Links do rodapé"><Link href="/docs">Docs</Link><a href={GITHUB}>GitHub</a><Link href="/login">Entrar</Link></nav></footer>
  </div>;
}
