"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy } from "lucide-react";
import { API_URL } from "@/lib/api";
import { AppHeader } from "@/components/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Lang = "pt" | "en";

const LANGS: { value: Lang; label: string }[] = [
  { value: "pt", label: "Português" },
  { value: "en", label: "English" },
];

const LANG_STORAGE_KEY = "docs-lang";

// Real responses, captured from a run of the transcription flow on this stack.
const EXAMPLE_JOB_ID = "7186e44b-3098-4590-9b5f-a29e9991e4e7";
const EXAMPLE_PROJECT_ID = "3f2b9c1e-5a7d-4e8b-9c0a-1d2e3f4a5b6c";

/**
 * Language of the page: `?lang=` wins (shareable links), then the last choice,
 * then the browser language. Portuguese is the default.
 */
function detectLang(): Lang {
  const fromQuery = new URLSearchParams(window.location.search).get("lang");
  if (fromQuery === "pt" || fromQuery === "en") return fromQuery;
  try {
    const stored = localStorage.getItem(LANG_STORAGE_KEY);
    if (stored === "pt" || stored === "en") return stored;
  } catch {
    // Storage can be blocked; fall through to the browser language.
  }
  return navigator.language.toLowerCase().startsWith("pt") ? "pt" : "en";
}

function CodeBlock({ code, copyLabel }: { code: string; copyLabel: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (insecure origin); the code stays selectable.
    }
  };

  return (
    <div className="relative">
      <pre className="bg-muted p-4 pr-12 rounded-lg overflow-x-auto text-sm leading-relaxed">
        <code>{code}</code>
      </pre>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={copy}
        className="absolute top-2 right-2 h-8 w-8 p-0"
        aria-label={copyLabel}
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </Button>
    </div>
  );
}

function Endpoint({ method, path }: { method: string; path: string }) {
  return (
    <div className="flex items-center gap-2 font-mono text-sm">
      <Badge variant={method === "GET" ? "secondary" : "default"}>{method}</Badge>
      <span className="break-all">{path}</span>
    </div>
  );
}

function Table({ head, rows }: { head?: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        {head && (
          <thead className="bg-muted/50">
            <tr>
              {head.map((h) => (
                <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={`align-top ${head || i > 0 ? "border-t" : ""}`}>
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="text-lg font-semibold pt-2">{children}</h3>;
}

function P({ children, small }: { children: React.ReactNode; small?: boolean }) {
  return <p className={small ? "text-sm text-muted-foreground" : "text-muted-foreground"}>{children}</p>;
}

function C({ children }: { children: React.ReactNode }) {
  return <code className="bg-muted px-1.5 py-0.5 rounded text-[0.85em]">{children}</code>;
}

function A({ href, children }: { href: string; children: React.ReactNode }) {
  const className = "text-primary underline underline-offset-4";
  return href.startsWith("/") ? (
    <Link href={href} className={className}>
      {children}
    </Link>
  ) : (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children}
    </a>
  );
}

// ---------------------------------------------------------------------------
// Code samples. Only the comments change between languages.
// ---------------------------------------------------------------------------

function samples(lang: Lang) {
  const pt = lang === "pt";
  const key = pt ? "SUA_CHAVE" : "YOUR_KEY";
  const file = pt ? "reuniao.mp3" : "meeting.mp3";
  const project = pt ? "Aulas" : "Lessons";

  return {
    curlCreate: `curl -X POST ${API_URL}/transcribe \\
  -H "X-API-Key: ${key}" \\
  -F "file=@${file}" \\
  -F "project=${project}" \\
  -F "language=pt" \\
  -F "output_format=vtt"`,

    curlProject: `# ${pt ? "Projeto e pasta por nome: criados se ainda não existirem" : "Project and folder by name: created if they do not exist yet"}
curl -X POST ${API_URL}/transcribe \\
  -H "X-API-Key: ${key}" \\
  -F "file=@${file}" \\
  -F "project=${pt ? "Cliente X" : "Client X"}" \\
  -F "folder=${pt ? "Reuniões" : "Meetings"}"

# ${pt ? "Projeto existente por ID (nunca cria)" : "An existing project by ID (never creates)"}
curl -X POST ${API_URL}/upload \\
  -H "X-API-Key: ${key}" \\
  -F "file=@${pt ? "contrato.pdf" : "contract.pdf"}" \\
  -F "project_id=${EXAMPLE_PROJECT_ID}"

# ${pt ? "Seus projetos, pastas e contagens" : "Your projects, folders and counts"}
curl "${API_URL}/projects?include=folders" -H "X-API-Key: ${key}"

# ${pt ? "Jobs de um projeto; folder_id=root = os que estão fora de pastas" : "Jobs of one project; folder_id=root = those in no folder"}
curl "${API_URL}/jobs?project_id=${EXAMPLE_PROJECT_ID}&folder_id=root" -H "X-API-Key: ${key}"`,

    curlStatus: `curl ${API_URL}/jobs/${EXAMPLE_JOB_ID} \\
  -H "X-API-Key: ${key}"`,

    curlLive: `# ${pt ? "Primeira chamada: tudo o que já foi transcrito" : "First call: everything transcribed so far"}
curl "${API_URL}/jobs/${EXAMPLE_JOB_ID}/transcript/partial" -H "X-API-Key: ${key}"

# ${pt ? "Depois, só o que é novo: passe o next da resposta anterior" : "Then only what is new: pass the previous response's next"}
curl "${API_URL}/jobs/${EXAMPLE_JOB_ID}/transcript/partial?since=2" -H "X-API-Key: ${key}"`,

    curlResult: `# ${pt ? "JSON com markdown + metadados" : "JSON with markdown + metadata"}
curl "${API_URL}/jobs/${EXAMPLE_JOB_ID}/result" -H "X-API-Key: ${key}"

# ${pt ? "Legenda WebVTT, salva em arquivo" : "WebVTT subtitles, saved to a file"}
curl "${API_URL}/jobs/${EXAMPLE_JOB_ID}/result?format=vtt" \\
  -H "X-API-Key: ${key}" -o ${pt ? "legenda" : "subtitles"}.vtt`,

    python: `import time
import requests

API = "${API_URL}"
HEADERS = {"X-API-Key": "${key}"}

# 1. ${pt ? "Envia o arquivo: a resposta volta na hora, com o job_id" : "Upload the file: the response comes back right away, with the job_id"}
with open("${file}", "rb") as f:
    r = requests.post(
        f"{API}/transcribe",
        headers=HEADERS,
        files={"file": f},
        data={"project": "${project}", "language": "pt", "output_format": "vtt"},
    )
r.raise_for_status()
job_id = r.json()["job_id"]

# 2. ${pt ? "Consulta o status até terminar" : "Poll the status until it finishes"}
while True:
    job = requests.get(f"{API}/jobs/{job_id}", headers=HEADERS).json()
    if job["status"] in ("completed", "failed"):
        break
    time.sleep(3)

if job["status"] == "failed":
    raise RuntimeError(job["error"])

# 3. ${pt ? "Baixa o resultado no formato desejado" : "Download the result in the format you want"}
vtt = requests.get(
    f"{API}/jobs/{job_id}/result",
    headers=HEADERS,
    params={"format": "vtt"},
).text
print(vtt)`,

    javascript: `const API = "${API_URL}";
const headers = { "X-API-Key": "${key}" };

// 1. ${pt ? "Envia o arquivo (em Node 18+, use fs.openAsBlob para ler do disco)" : "Upload the file (on Node 18+, use fs.openAsBlob to read it from disk)"}
const form = new FormData();
form.append("file", ${pt ? "arquivo" : "file"}); // ${pt ? "um File/Blob, ex.: de um <input type=\"file\">" : "a File/Blob, e.g. from an <input type=\"file\">"}
form.append("project", "${project}");
form.append("language", "pt");
form.append("output_format", "vtt");

const created = await fetch(\`\${API}/transcribe\`, { method: "POST", headers, body: form });
if (!created.ok) throw new Error((await created.json()).detail);
const { job_id } = await created.json();

// 2. ${pt ? "Consulta o status até terminar" : "Poll the status until it finishes"}
let job;
do {
  await new Promise((r) => setTimeout(r, 3000));
  job = await (await fetch(\`\${API}/jobs/\${job_id}\`, { headers })).json();
} while (job.status !== "completed" && job.status !== "failed");

if (job.status === "failed") throw new Error(job.error);

// 3. ${pt ? "Baixa o resultado no formato desejado" : "Download the result in the format you want"}
const vtt = await (await fetch(\`\${API}/jobs/\${job_id}/result?format=vtt\`, { headers })).text();`,
  };
}

// API responses are the same in both languages: the server answers in Portuguese.
const RESPONSES = {
  create: `{
  "job_id": "${EXAMPLE_JOB_ID}",
  "status": "queued",
  "created_at": "2026-09-25T18:32:29.301477",
  "message": "Job de transcrição de áudio enfileirado para processamento",
  "project": { "id": "${EXAMPLE_PROJECT_ID}", "name": "Aulas", "created": false, "source": "request" },
  "folder": null
}`,
  projectRequired: `HTTP/1.1 422 Unprocessable Entity

{
  "detail": "Informe o projeto do upload: campo 'project' (nome; é criado se não existir) ou\\n'project_id'. Exemplo: curl -H \\"X-API-Key: ...\\" -F \\"file=@arquivo.mp3\\" -F \\"project=Aulas\\" .../transcribe\\nPara não precisar enviar o projeto, vincule a API key a um projeto em /api-keys."
}`,
  status: `{
  "job_id": "${EXAMPLE_JOB_ID}",
  "type": "main",
  "status": "processing",
  "progress": 51,
  "transcribed_seconds": 960.4,
  "media_duration": 1821.0,
  "created_at": "2026-09-25T18:32:29",
  "started_at": "2026-09-25T18:32:38",
  "completed_at": null,
  "error": null,
  ...
}`,
  live: `{
  "job_id": "${EXAMPLE_JOB_ID}",
  "status": "processing",
  "segments": [
    { "start": 0.0, "end": 4.2, "text": "Olá, este é um teste da API de transcrição." },
    { "start": 4.2, "end": 9.8, "text": "O áudio é enviado, entra na fila e o worker transcreve." }
  ],
  "next": 2
}`,
  markdown: `{
  "job_id": "${EXAMPLE_JOB_ID}",
  "type": "main",
  "status": "completed",
  "result": {
    "markdown": "# Audio Transcription\\n\\n**Language:** pt\\n**Duration:** 10.67s\\n**Word Count:** 25\\n\\n---\\n\\n[00:00] Olá, este é um teste da API de transcrição...\\n[00:04] O áudio é enviado, entra na fila e o worker transcreve usando a GPU.",
    "metadata": {
      "words": 25,
      "format": "mp3",
      "size_bytes": 86143,
      "language": "pt",
      "duration": 10.667625,
      "device": "cuda",
      "available_formats": ["markdown", "vtt", "srt", "txt", "json"]
    }
  },
  "completed_at": "2026-09-25T18:33:28"
}`,
  vtt: `WEBVTT

1
00:00:00.000 --> 00:00:04.360
Olá, este é um teste da API de transcrição...

2
00:00:04.860 --> 00:00:10.100
O áudio é enviado, entra na fila e o worker transcreve usando a GPU.`,
  srt: `1
00:00:00,000 --> 00:00:04,360
Olá, este é um teste da API de transcrição...

2
00:00:04,860 --> 00:00:10,100
O áudio é enviado, entra na fila e o worker transcreve usando a GPU.`,
  txt: `Olá, este é um teste da API de transcrição...
O áudio é enviado, entra na fila e o worker transcreve usando a GPU.`,
  json: `{
  "language": "pt",
  "duration": 10.667625,
  "text": "Olá, este é um teste da API de transcrição... O áudio é enviado, ...",
  "segments": [
    { "start": 0.0,  "end": 4.36, "text": "Olá, este é um teste da API de transcrição..." },
    { "start": 4.86, "end": 10.1, "text": "O áudio é enviado, entra na fila e o worker transcreve usando a GPU." }
  ]
}`,
};

// ---------------------------------------------------------------------------
// Prose. Each language is a full copy so neither reads like a translation.
// ---------------------------------------------------------------------------

const JOB = <C>/jobs/&#123;job_id&#125;/result</C>;

const COPY = {
  pt: {
    copy: "Copiar código",
    sidebarTitle: "Documentação da API",
    comingSoon: "Consulte o Swagger para a referência completa, incluindo busca.",
    sections: {
      intro: "Introdução",
      auth: "Autenticação",
      projects: "Projetos e pastas",
      documents: "PDF e documentos",
      pages: "Páginas de PDF",
      images: "Imagens: descrição e OCR",
      transcribe: "Transcrição de áudio e vídeo",
      status: "Acompanhar o job",
      live: "Legendas de arquivos",
      result: "Baixar o resultado",
      errors: "Erros",
    },
    intro: (
      <P>
        A API do Ingestify é REST e assíncrona: você envia um arquivo, recebe um <C>job_id</C> na hora,
        acompanha o processamento e depois baixa o resultado. As rotas de imagem esperam a inferência e
        devolvem descrição ou OCR na mesma requisição, com um prazo de espera.
      </P>
    ),
    introRows: [
      ["URL base", <C key="u">{API_URL}</C>],
      ["Formato", "JSON nas respostas; multipart/form-data nos uploads"],
      ["Idioma das mensagens", "As mensagens da API (message, detail) vêm em português"],
      ["Referência completa", <A key="s" href={`${API_URL}/docs`}>{API_URL}/docs (Swagger)</A>],
    ],
    authIntro: <P>Toda chamada precisa estar autenticada, de uma destas duas formas:</P>,
    authHead: ["Header", "Quando usar"],
    authRows: [
      [
        <C key="k">X-API-Key: SUA_CHAVE</C>,
        <span key="d">
          Integrações e scripts. Crie a chave em <A href="/api-keys">API Keys</A>; ela só é exibida uma vez.
        </span>,
      ],
      [
        <C key="b">Authorization: Bearer TOKEN</C>,
        <span key="d">
          Sessão de usuário. O token vem de <C>POST /auth/login</C> (form com <C>username</C> e{" "}
          <C>password</C>) e expira.
        </span>,
      ],
    ],
    authNote: (
      <P small>
        Sem credencial válida a API responde <C>401</C>. Cada usuário só enxerga os próprios jobs: um{" "}
        <C>job_id</C> de outra pessoa responde <C>404</C>.
      </P>
    ),
    projectsIntro: (
      <P>
        Todo job pertence a exatamente um <strong>projeto</strong> seu e, opcionalmente, a uma{" "}
        <strong>pasta</strong> desse projeto (um nível só). O projeto é obrigatório em todo upload (
        <C>/upload</C>, <C>/convert</C>, <C>/transcribe</C>, <C>/images/…</C>); a pasta, não.
      </P>
    ),
    projectsHead: ["Campo", "Significado"],
    projectsRows: [
      [<C key="p">project</C>, "Nome do projeto. Se não existir, é criado (get-or-add)."],
      [<C key="pi">project_id</C>, "ID de um projeto existente. Nunca cria. Não pode vir junto com project."],
      [<C key="f">folder</C>, "Nome da pasta dentro do projeto. Se não existir, é criada. Não pode conter “/”."],
      [<C key="fi">folder_id</C>, "ID de uma pasta existente; precisa ser do projeto do upload."],
    ],
    projectsResolution: (
      <P>
        O projeto vem do request (<C>project</C> ou <C>project_id</C>). Se o request não diz, vale o projeto
        vinculado à API key usada (veja <A href="/api-keys">API Keys</A>). Sem nenhum dos dois, a API responde{" "}
        <C>422</C> e nada é gravado:
      </P>
    ),
    projectsNormalization: (
      <P small>
        Nomes são comparados sem diferenciar maiúsculas, espaços repetidos e acentos sobre letras latinas:{" "}
        <C>reuniao   SEMANAL</C> cai no projeto “Reunião Semanal”. Outros alfabetos não são alterados. Até 100
        caracteres.
      </P>
    ),
    projectsPrecedence: (
      <P small>
        Com <C>Authorization: Bearer</C> e <C>X-API-Key</C> no mesmo request, vale o token, e o projeto
        vinculado à key não é usado. Arquivos repetidos só são reaproveitados dentro do mesmo projeto: o mesmo
        arquivo enviado a outro projeto é processado de novo.
      </P>
    ),
    projectsExampleTitle: "Exemplos",
    projectsRequiredTitle: "Upload sem projeto — 422",
    transcribeIntro: (
      <P>
        Transcreve a fala de um áudio ou vídeo (Whisper). Do vídeo, só a faixa de áudio é usada. A resposta
        volta imediatamente com o <C>job_id</C>; a transcrição roda em segundo plano, na GPU quando disponível
        (com fallback automático para CPU). Todos os formatos de saída são gerados de uma vez: Markdown,
        legendas VTT e SRT, texto puro e JSON com segmentos.
      </P>
    ),
    paramsTitle: "Parâmetros (multipart/form-data)",
    paramsHead: ["Campo", "Tipo", "Padrão", "Descrição"],
    paramsRows: [
      [<C key="f">file</C>, "arquivo", <em key="r">obrigatório</em>, "O áudio ou vídeo."],
      [
        <span key="p">
          <C>project</C> ou <C>project_id</C>
        </span>,
        "texto / uuid",
        <span key="r">
          <em>obrigatório</em>, salvo key vinculada
        </span>,
        <span key="d">
          Projeto do job, por nome (criado se não existir) ou por ID. Veja{" "}
          <a href="#projetos" className="text-primary underline-offset-4 hover:underline">
            Projetos e pastas
          </a>
          .
        </span>,
      ],
      [
        <span key="p">
          <C>folder</C> ou <C>folder_id</C>
        </span>,
        "texto / uuid",
        "nenhuma",
        "Pasta dentro do projeto, por nome (criada se não existir) ou por ID.",
      ],
      [<C key="n">name</C>, "texto", "nome do arquivo", "Nome para identificar o job na lista."],
      [
        <C key="tg">tags</C>,
        "texto",
        "nenhuma",
        <span key="d">
          Tags separadas por vírgula (<C>cliente-x, reunião</C>). Viram minúsculas; até 20 de até 50
          caracteres. Filtre depois com <C>GET /jobs?tag=cliente-x</C>. Reenviar o mesmo arquivo adiciona as
          tags ao job existente.
        </span>,
      ],
      [
        <C key="l">language</C>,
        "texto",
        "detecção automática",
        <span key="d">
          Código ISO 639-1 do idioma falado (<C>pt</C>, <C>en</C>, <C>es</C>…). Informar melhora a precisão e
          evita erro de detecção em áudios curtos.
        </span>,
      ],
      [
        <C key="t">include_timestamps</C>,
        "booleano",
        <C key="v">true</C>,
        <span key="d">
          Marcadores <C>[MM:SS]</C> no Markdown.
        </span>,
      ],
      [
        <C key="w">include_word_timestamps</C>,
        "booleano",
        <C key="v">false</C>,
        <span key="d">
          Tempo de cada palavra (com <C>probability</C>) nos segmentos do formato <C>json</C>.
        </span>,
      ],
      [
        <C key="o">output_format</C>,
        "texto",
        <C key="v">markdown</C>,
        <span key="d">
          Formato devolvido por {JOB} quando você não passa <C>?format=</C>: <C>markdown</C>, <C>vtt</C>,{" "}
          <C>srt</C>, <C>txt</C> ou <C>json</C>. Os outros continuam disponíveis.
        </span>,
      ],
    ],
    filesTitle: "Arquivos aceitos",
    filesHead: ["Tipo", "Formatos", "Tamanho máximo"],
    filesRows: [
      ["Áudio", "MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC", "50 MB"],
      ["Vídeo", "MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP", "500 MB"],
    ],
    filesNote: (
      <P small>
        O tipo é reconhecido pelo MIME type ou pela extensão. Os limites são configuráveis no servidor (
        <C>MAX_AUDIO_FILE_SIZE_MB</C>, <C>MAX_VIDEO_FILE_SIZE_MB</C>).
      </P>
    ),
    exampleTitle: "Exemplo completo",
    responseTitle: "Resposta — 200",
    duplicate: (
      <>
        <strong className="text-foreground">Arquivo repetido:</strong> se você já enviou exatamente o mesmo
        arquivo <em>para o mesmo projeto</em>, nenhum job novo é criado. A resposta traz o <C>job_id</C> do job existente (com{" "}
        <C>status: &quot;queued&quot;</C> e uma mensagem avisando). Consulte o status dele normalmente — pode já
        estar concluído. O <C>output_format</C> do novo envio passa a valer para esse job.
      </>
    ),
    statusIntro: (
      <P>
        Consulte a cada poucos segundos até <C>status</C> ser <C>completed</C> ou <C>failed</C>. Os estados
        possíveis são <C>queued</C>, <C>processing</C>, <C>completed</C> e <C>failed</C>; <C>progress</C> vai
        de 0 a 100 e, se falhar, <C>error</C> explica o motivo.
      </P>
    ),
    statusFields: (
      <P small>
        Durante a transcrição, <C>transcribed_seconds</C> de <C>media_duration</C> mostra até onde o áudio já foi
        transcrito, em segundos. Quando o servidor distribui o trabalho entre motores (a GPU local e contas na
        nuvem), o status também traz <C>engine.kind</C> (<C>local</C> ou <C>cloud</C>) e, enquanto espera,{" "}
        <C>queue_reason</C> (<C>in_queue</C>: aguardando vaga; <C>starting</C>: a GPU na nuvem está ligando). Sem
        esse roteamento configurado, os dois campos vêm <C>null</C>.
      </P>
    ),
    liveIntro: (
      <P>
        Enquanto um job está em <C>processing</C>, o texto já transcrito pode ser lido por trechos, sem esperar o
        fim. A resposta traz os segmentos a partir de <C>since</C> e, em <C>next</C>, o valor a passar na próxima
        consulta, para receber só o que é novo. Quando o job termina a lista fica vazia: o texto completo está em{" "}
        {JOB}.
      </P>
    ),
    statusNote: (
      <P small>
        Referência medida na GPU: um áudio de 10 segundos levou cerca de 1 minuto na primeira transcrição (o
        worker carrega o modelo) e cerca de 10 segundos nas seguintes, contando a fila. Consultar a cada 2–5
        segundos é suficiente.
      </P>
    ),
    resultIntro: (
      <P>
        Sem <C>?format=</C>, vale o <C>output_format</C> escolhido no envio. Com ele, você pede qualquer formato
        a qualquer momento — todos foram gerados. Os formatos de arquivo vêm com <C>Content-Disposition</C> e
        podem ser salvos direto.
      </P>
    ),
    formatsHead: ["format", "Content-Type", "Conteúdo"],
    formatsDesc: {
      markdown: "Transcrição em Markdown + metadados (idioma, duração, device).",
      vtt: "Legenda WebVTT, pronta para <track> em HTML5.",
      srt: "Legenda SRT para players e editores de vídeo.",
      txt: "Só o texto, um segmento por linha.",
      json: "Texto, duração e segmentos com início/fim em segundos.",
    },
    deviceNote: (
      <>
        <C>metadata.device</C> diz onde a transcrição rodou: <C>cuda</C> (GPU deste servidor), <C>cpu</C>,{" "}
        <C>modal:L4</C> (GPU na nuvem, com o tipo da placa) ou <C>remote</C> (API externa).
      </>
    ),
    wordsNote: (
      <>
        Com <C>include_word_timestamps=true</C>, cada segmento ganha uma lista <C>words</C> com <C>word</C>,{" "}
        <C>start</C>, <C>end</C> e <C>probability</C>.
      </>
    ),
    errorsIntro: (
      <P>
        Erros vêm como JSON com o campo <C>detail</C> explicando o problema.
      </P>
    ),
    errorsHead: ["Status", "Quando"],
    errors: {
      "401": "Sem credencial, chave inválida ou token expirado.",
      "400": "Arquivo vazio; ou, em /result, o job ainda está em processamento.",
      "404": "Job, projeto ou pasta inexistente ou de outro usuário, ou formato pedido indisponível (ex.: ?format=vtt num job de documento).",
      "413": "Arquivo acima do limite de tamanho.",
      "422": "Formato de arquivo não suportado, output_format/format inválido, upload sem projeto, ou nome de projeto/pasta inválido.",
      "500": "Em /result: o job falhou (o motivo vem em detail).",
      "503": "Transcrição desabilitada no servidor ou workers indisponíveis.",
    },
  },

  en: {
    copy: "Copy code",
    sidebarTitle: "API documentation",
    comingSoon: "See Swagger for the full reference, including search.",
    sections: {
      intro: "Introduction",
      auth: "Authentication",
      projects: "Projects and folders",
      documents: "PDF and documents",
      pages: "PDF pages",
      images: "Images: description and OCR",
      transcribe: "Audio and video transcription",
      status: "Track the job",
      live: "File captions",
      result: "Download the result",
      errors: "Errors",
    },
    intro: (
      <P>
        The Ingestify API is REST and asynchronous: you upload a file, get a <C>job_id</C> right away, track
        the processing and then download the result. Image routes wait for inference and return a
        description or OCR in the same request, within a time budget.
      </P>
    ),
    introRows: [
      ["Base URL", <C key="u">{API_URL}</C>],
      ["Format", "JSON responses; multipart/form-data for uploads"],
      ["Message language", "API messages (message, detail) are in Portuguese"],
      ["Full reference", <A key="s" href={`${API_URL}/docs`}>{API_URL}/docs (Swagger)</A>],
    ],
    authIntro: <P>Every call must be authenticated, in one of two ways:</P>,
    authHead: ["Header", "When to use it"],
    authRows: [
      [
        <C key="k">X-API-Key: YOUR_KEY</C>,
        <span key="d">
          Integrations and scripts. Create the key under <A href="/api-keys">API Keys</A>; it is shown only once.
        </span>,
      ],
      [
        <C key="b">Authorization: Bearer TOKEN</C>,
        <span key="d">
          User sessions. The token comes from <C>POST /auth/login</C> (a form with <C>username</C> and{" "}
          <C>password</C>) and expires.
        </span>,
      ],
    ],
    authNote: (
      <P small>
        Without valid credentials the API answers <C>401</C>. Users only see their own jobs: another
        person&apos;s <C>job_id</C> answers <C>404</C>.
      </P>
    ),
    projectsIntro: (
      <P>
        Every job belongs to exactly one of your <strong>projects</strong> and, optionally, to a{" "}
        <strong>folder</strong> in that project (one level only). The project is required on every upload (
        <C>/upload</C>, <C>/convert</C>, <C>/transcribe</C>, <C>/images/…</C>); the folder is not.
      </P>
    ),
    projectsHead: ["Field", "Meaning"],
    projectsRows: [
      [<C key="p">project</C>, "Project name. Created if it does not exist (get-or-add)."],
      [<C key="pi">project_id</C>, "ID of an existing project. Never creates. Not allowed together with project."],
      [<C key="f">folder</C>, "Folder name inside the project. Created if it does not exist. Cannot contain “/”."],
      [<C key="fi">folder_id</C>, "ID of an existing folder; it must belong to the upload's project."],
    ],
    projectsResolution: (
      <P>
        The project comes from the request (<C>project</C> or <C>project_id</C>). When the request names none,
        the project bound to the API key is used (see <A href="/api-keys">API Keys</A>). With neither, the API
        answers <C>422</C> and nothing is stored:
      </P>
    ),
    projectsNormalization: (
      <P small>
        Names are matched ignoring case, repeated spaces and accents on Latin letters: <C>reuniao   SEMANAL</C>{" "}
        lands in the “Reunião Semanal” project. Other scripts are left as they are. Up to 100 characters.
      </P>
    ),
    projectsPrecedence: (
      <P small>
        With both <C>Authorization: Bearer</C> and <C>X-API-Key</C> on one request, the token wins and the
        key&apos;s project is not used. Repeated files are only reused within the same project: the same file
        sent to another project is processed again.
      </P>
    ),
    projectsExampleTitle: "Examples",
    projectsRequiredTitle: "Upload with no project — 422",
    transcribeIntro: (
      <P>
        Transcribes the speech in an audio or video file (Whisper). For video, only the audio track is used. The
        response comes back immediately with the <C>job_id</C>; the transcription runs in the background, on the
        GPU when available (falling back to CPU automatically). Every output format is produced at once:
        Markdown, VTT and SRT subtitles, plain text and JSON with segments.
      </P>
    ),
    paramsTitle: "Parameters (multipart/form-data)",
    paramsHead: ["Field", "Type", "Default", "Description"],
    paramsRows: [
      [<C key="f">file</C>, "file", <em key="r">required</em>, "The audio or video."],
      [
        <span key="p">
          <C>project</C> or <C>project_id</C>
        </span>,
        "string / uuid",
        <span key="r">
          <em>required</em>, unless the key is bound
        </span>,
        <span key="d">
          The job&apos;s project, by name (created if new) or by ID. See{" "}
          <a href="#projetos" className="text-primary underline-offset-4 hover:underline">
            Projects and folders
          </a>
          .
        </span>,
      ],
      [
        <span key="p">
          <C>folder</C> or <C>folder_id</C>
        </span>,
        "string / uuid",
        "none",
        "A folder inside the project, by name (created if new) or by ID.",
      ],
      [<C key="n">name</C>, "string", "file name", "Name that identifies the job in your list."],
      [
        <C key="tg">tags</C>,
        "string",
        "none",
        <span key="d">
          Comma-separated tags (<C>client-x, meeting</C>). Lower-cased; up to 20 of up to 50 characters. Filter
          later with <C>GET /jobs?tag=client-x</C>. Re-uploading the same file adds the tags to the existing job.
        </span>,
      ],
      [
        <C key="l">language</C>,
        "string",
        "auto-detected",
        <span key="d">
          ISO 639-1 code of the spoken language (<C>pt</C>, <C>en</C>, <C>es</C>…). Setting it improves accuracy
          and avoids misdetection on short clips.
        </span>,
      ],
      [
        <C key="t">include_timestamps</C>,
        "boolean",
        <C key="v">true</C>,
        <span key="d">
          <C>[MM:SS]</C> markers in the Markdown.
        </span>,
      ],
      [
        <C key="w">include_word_timestamps</C>,
        "boolean",
        <C key="v">false</C>,
        <span key="d">
          Timing for every word (with <C>probability</C>) in the segments of the <C>json</C> format.
        </span>,
      ],
      [
        <C key="o">output_format</C>,
        "string",
        <C key="v">markdown</C>,
        <span key="d">
          Format returned by {JOB} when you don&apos;t pass <C>?format=</C>: <C>markdown</C>, <C>vtt</C>,{" "}
          <C>srt</C>, <C>txt</C> or <C>json</C>. The others remain available.
        </span>,
      ],
    ],
    filesTitle: "Accepted files",
    filesHead: ["Type", "Formats", "Max size"],
    filesRows: [
      ["Audio", "MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC", "50 MB"],
      ["Video", "MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP", "500 MB"],
    ],
    filesNote: (
      <P small>
        The type is recognised by MIME type or file extension. Limits are configurable on the server (
        <C>MAX_AUDIO_FILE_SIZE_MB</C>, <C>MAX_VIDEO_FILE_SIZE_MB</C>).
      </P>
    ),
    exampleTitle: "Full example",
    responseTitle: "Response — 200",
    duplicate: (
      <>
        <strong className="text-foreground">Repeated file:</strong> if you already uploaded the exact same file{" "}
        <em>to the same project</em>, no new job is created. The response carries the existing job&apos;s <C>job_id</C> (with{" "}
        <C>status: &quot;queued&quot;</C> and a message saying so). Check its status as usual — it may already be
        done. The <C>output_format</C> of the new request becomes that job&apos;s default.
      </>
    ),
    statusIntro: (
      <P>
        Poll every few seconds until <C>status</C> is <C>completed</C> or <C>failed</C>. The possible states are{" "}
        <C>queued</C>, <C>processing</C>, <C>completed</C> and <C>failed</C>; <C>progress</C> goes from 0 to 100
        and, on failure, <C>error</C> explains why.
      </P>
    ),
    statusFields: (
      <P small>
        While transcribing, <C>transcribed_seconds</C> of <C>media_duration</C> shows how far into the audio the
        transcription is, in seconds. When the server spreads work across engines (this server&apos;s GPU and cloud
        accounts), the status also carries <C>engine.kind</C> (<C>local</C> or <C>cloud</C>) and, while it waits,{" "}
        <C>queue_reason</C> (<C>in_queue</C>: waiting for a slot; <C>starting</C>: the cloud GPU is starting up).
        Without that routing configured, both fields are <C>null</C>.
      </P>
    ),
    liveIntro: (
      <P>
        While a job is <C>processing</C>, the text transcribed so far can be read in pieces, without waiting for the
        end. The response carries the segments from <C>since</C> on and, in <C>next</C>, the value to pass on the
        next call so you only get what is new. Once the job finishes the list is empty: the full text is at {JOB}.
      </P>
    ),
    statusNote: (
      <P small>
        Measured on the GPU: a 10-second clip took about 1 minute on the first transcription (the worker loads
        the model) and about 10 seconds afterwards, queue included. Polling every 2–5 seconds is enough.
      </P>
    ),
    resultIntro: (
      <P>
        Without <C>?format=</C>, the <C>output_format</C> chosen at upload applies. With it, you can ask for any
        format at any time — all of them were produced. File formats come with <C>Content-Disposition</C> and can
        be saved directly.
      </P>
    ),
    formatsHead: ["format", "Content-Type", "Contents"],
    formatsDesc: {
      markdown: "Markdown transcript + metadata (language, duration, device).",
      vtt: "WebVTT subtitles, ready for an HTML5 <track>.",
      srt: "SRT subtitles for players and video editors.",
      txt: "Plain text, one segment per line.",
      json: "Text, duration and segments with start/end in seconds.",
    },
    deviceNote: (
      <>
        <C>metadata.device</C> tells where the transcription ran: <C>cuda</C> (this server&apos;s GPU),{" "}
        <C>cpu</C>, <C>modal:L4</C> (a cloud GPU, with the card type) or <C>remote</C> (an external API).
      </>
    ),
    wordsNote: (
      <>
        With <C>include_word_timestamps=true</C>, every segment gets a <C>words</C> list with <C>word</C>,{" "}
        <C>start</C>, <C>end</C> and <C>probability</C>.
      </>
    ),
    errorsIntro: (
      <P>
        Errors are JSON, with a <C>detail</C> field describing the problem.
      </P>
    ),
    errorsHead: ["Status", "When"],
    errors: {
      "401": "No credentials, invalid key or expired token.",
      "400": "Empty file; or, on /result, the job is still processing.",
      "404": "Job, project or folder doesn't exist or belongs to another user, or the requested format isn't available (e.g. ?format=vtt on a document job).",
      "413": "File above the size limit.",
      "422": "Unsupported file type, invalid output_format/format, an upload with no project, or an invalid project/folder name.",
      "500": "On /result: the job failed (the reason is in detail).",
      "503": "Transcription disabled on the server, or no workers available.",
    },
  },
};

const FORMAT_TYPES: [keyof typeof COPY.pt.formatsDesc, string][] = [
  ["markdown", "application/json"],
  ["vtt", "text/vtt"],
  ["srt", "application/x-subrip"],
  ["txt", "text/plain"],
  ["json", "application/json"],
];

const MEDIA_COPY = {
  pt: {
    docsIntro: "Converte PDFs e documentos em Markdown com Docling. /upload recebe um arquivo e devolve job_id imediatamente. /convert também recebe fontes externas; ambos usam multipart/form-data.",
    fields: ["Campo", "Uso"],
    docsRows: [
      ["file", "Obrigatório no /upload; no /convert quando source_type=file. Até 50 MB por padrão (MAX_FILE_SIZE_MB)."],
      ["project / project_id", "Projeto obrigatório, salvo API key vinculada. folder / folder_id são opcionais; veja Projetos e pastas."],
      ["name / tags", "Nome opcional e tags separadas por vírgula. O padrão de name é o nome do arquivo."],
      ["docling_preset", "Apenas /upload: fast (padrão), balanced ou quality. /convert usa as opções DOCLING_* do servidor."],
      ["source_type / source", "No /convert: file + file; url + URL pública HTTP(S); gdrive + ID; dropbox + caminho."],
      ["X-Source-Token", "Header obrigatório para gdrive e dropbox: token do provedor, separado da autenticação do Ingestify."],
    ],
    presetsTitle: "Escolher velocidade e OCR",
    presetsHead: ["Preset", "OCR", "Imagens", "Tabelas", "Uso"],
    presets: [["fast", "não", "não", "sim", "PDF digital"], ["balanced", "não", "sim", "sim", "PDF com figuras"], ["quality", "sim", "sim", "sim", "PDF escaneado; mais lento"]],
    formats: "PDF, DOCX, HTML, PPTX e XLSX dependem do suporte da versão instalada do Docling. A API aceita o upload antes de validar a conversão: um arquivo incompatível termina com status failed. DOC/PPT/XLS legados, RTF e ODT não têm sucesso garantido.",
    docsDuplicate: "O mesmo arquivo no mesmo projeto reaproveita um job que não esteja failed e adiciona as tags. A pasta do job existente é preservada; trocar o preset no reenvio não força outra conversão. Um arquivo em outro projeto é processado novamente.",
    docsResult: "Consulte /jobs/{job_id} a cada poucos segundos e leia result.markdown de /jobs/{job_id}/result quando completed. Documentos não geram VTT/SRT. /result retorna 400 enquanto o job processa, 500 se falhou e 404 se o status/resultado expirou.",
    example: "Exemplos de requisição",
    resultExample: "Exemplo ilustrativo de resultado",
    pagesIntro: "PDFs com duas ou mais páginas são divididos e convertidos em paralelo; o Markdown final reúne as páginas em ordem. Use o ID principal e números de página começando em 1. Um PDF de uma página é convertido inteiro e não tem jobs de página.",
    pagesHead: ["Endpoint", "Uso"],
    pagesRows: [
      ["GET /jobs/{id}/pages", "Lista total_pages, pages_completed, pages_failed e pages[] com page_number, job_id, status, url, error_message e retry_count."],
      ["GET /jobs/{id}/pages/{n}/status", "Status de uma página pelo número."],
      ["GET /jobs/{id}/pages/{n}/result", "JSON com result.markdown de uma página concluída; não precisa aguardar o merge."],
      ["GET /jobs/{id}/pages/{n}/pdf", "JSON com url assinada do PDF, expires_in=900 e expires_at; não devolve os bytes do PDF."],
      ["POST /jobs/{id}/pages/{n}/retry", "Reprocessa uma página failed, até 3 tentativas manuais; guarde o novo page_job_id retornado."],
    ],
    pagesNote: "Antes do split, /pages pode responder 404; durante a criação, pages[] pode estar incompleto e job_id pode ser null. Consulte novamente. Páginas failed bloqueiam o merge até serem recuperadas. Todos os endpoints exigem autenticação e verificam o dono.",
    pdfNote: "Abra a url assinada diretamente, sem Authorization ou X-API-Key. Ela vale por 15 minutos; peça outra quando expirar e preserve toda a query string. Não acrescente parâmetros à URL.",
    engineNote: "O servidor pode rotear páginas por motores de execução quando configurado. Você continua usando os mesmos endpoints; presets e filas não são escolhidos por um parâmetro engine no upload.",
    imagesIntro: "Florence-2 descreve imagens ou extrai texto com regiões (OCR). As quatro rotas de inferência criam um job e esperam o resultado na mesma requisição. O prazo padrão é 60 segundos; a task pode continuar até o seu limite de 120 segundos, configuráveis no servidor.",
    imagesHead: ["Endpoint", "Entrada / saída"],
    imagesRows: [
      ["POST /images/describe/upload", "multipart: file, task opcional, tags, project/project_id e folder/folder_id. Retorna description e task."],
      ["POST /images/describe", "JSON: image_base64, filename opcional, task, tags como lista e localização. Mesma resposta de descrição."],
      ["POST /images/ocr/upload", "multipart: file, tags e localização. Retorna text e lines[]."],
      ["POST /images/ocr", "JSON: image_base64, filename opcional, tags como lista e localização. Mesmo OCR; não recebe task."],
      ["GET /images/capabilities", "Estado do worker: dependencies_installed, model_downloaded, model_loaded, device_resolved e reason. Exige autenticação; não inicia inferência."],
    ],
    imageOptions: "PNG, JPEG, WEBP, BMP, GIF e TIFF, detectados pelos bytes. Limite padrão: 10 MB de imagem decodificada e 50 milhões de pixels (VISION_MAX_IMAGE_SIZE_MB / VISION_MAX_IMAGE_PIXELS). Base64 aceita prefixo data:image/...;base64, e quebras de linha. O projeto é obrigatório pelas mesmas regras dos documentos; imagem repetida cria outro job.",
    imageTasks: "task aceita apenas <CAPTION>, <DETAILED_CAPTION> e <MORE_DETAILED_CAPTION> (padrão, configurável por VISION_CAPTION_TASK). Não aceita um prompt livre. Em curl, use --form-string para esses valores: -F interpreta o caractere < como leitura de arquivo.",
    imageResponse: "Sucesso (200): job_id, status=completed, project, folder, image_base64 (eco dos bytes originais), image_mime_type, image_bytes, image_sha256, width, height, model (model_id, revision, device, dtype) e duration_ms, além da descrição ou do OCR. duration_ms mede o processamento reportado pelo worker; não é o tempo total da requisição.",
    ocrNote: "Cada linha tem text, quad_box=[x1,y1,x2,y2,x3,y3,x4,y4] e bbox=[x_min,y_min,x_max,y_max], em pixels da imagem original. Imagem sem texto retorna 200, text vazio e lines=[]. O exemplo abaixo mostra apenas os campos de OCR.",
    timeoutTitle: "Timeout e limites atuais",
    timeout: "Um 504 VISION_TIMEOUT traz detail.job_id, poll_url e result_url; a task continua. Consulte poll_url para o status e evite reenviar automaticamente. Limitação atual: /jobs/{id}/result exige Markdown, mas o resultado de visão não tem esse campo; após completar, essa recuperação pode falhar com 500. Salve a resposta de sucesso da própria chamada de imagem.",
    retention: "O resultado de visão fica no Redis por RESULT_TTL_SECONDS (1 hora por padrão), sem persistência em Elasticsearch/MinIO. A imagem temporária é apagada pelo worker. O status de sucesso não é atualizado no MySQL; após expirar o cache, a listagem pode voltar a queued.",
    imageErrors: "Erros de visão geralmente usam detail={error_code,message,job_id}; erros de autenticação e validação podem ter outro formato. 413: tamanho; 422: base64, formato, task, pixels ou localização inválidos; 503: visão desabilitada, worker/modelo indisponível ou motor sem vaga (VISION_ENGINE_UNAVAILABLE, com Retry-After). /capabilities também responde 503 se a visão estiver desabilitada.",
  },
  en: {
    docsIntro: "Converts PDFs and documents to Markdown with Docling. /upload accepts a file and immediately returns job_id. /convert also accepts external sources; both use multipart/form-data.",
    fields: ["Field", "Usage"],
    docsRows: [
      ["file", "Required on /upload; on /convert when source_type=file. Default limit: 50 MB (MAX_FILE_SIZE_MB)."],
      ["project / project_id", "Required unless the API key is bound to a project. folder / folder_id are optional; see Projects and folders."],
      ["name / tags", "Optional display name and comma-separated tags. name defaults to the file name."],
      ["docling_preset", "/upload only: fast (default), balanced or quality. /convert uses the server's DOCLING_* settings."],
      ["source_type / source", "On /convert: file + file; url + public HTTP(S) URL; gdrive + ID; dropbox + path."],
      ["X-Source-Token", "Required header for gdrive and dropbox: the provider token, separate from Ingestify authentication."],
    ],
    presetsTitle: "Choosing speed and OCR",
    presetsHead: ["Preset", "OCR", "Images", "Tables", "Usage"],
    presets: [["fast", "no", "no", "yes", "Digital PDF"], ["balanced", "no", "yes", "yes", "PDF with figures"], ["quality", "yes", "yes", "yes", "Scanned PDF; slower"]],
    formats: "PDF, DOCX, HTML, PPTX and XLSX depend on the installed Docling version. The API accepts the upload before validating conversion: an incompatible file ends with status failed. Legacy DOC/PPT/XLS, RTF and ODT are not guaranteed to convert.",
    docsDuplicate: "The same file in the same project reuses a job that is not failed and adds the supplied tags. The existing job's folder is preserved; changing the preset on re-upload does not force conversion. Uploading to another project processes the file again.",
    docsResult: "Poll /jobs/{job_id} every few seconds and read result.markdown from /jobs/{job_id}/result once completed. Documents do not produce VTT/SRT. /result returns 400 while processing, 500 on failure and 404 if the status/result has expired.",
    example: "Request examples",
    resultExample: "Illustrative result example",
    pagesIntro: "PDFs with two or more pages are split and converted in parallel; the final Markdown joins them in order. Use the main job ID and page numbers starting at 1. A single-page PDF is converted as a whole and has no page jobs.",
    pagesHead: ["Endpoint", "Usage"],
    pagesRows: [
      ["GET /jobs/{id}/pages", "Lists total_pages, pages_completed, pages_failed and pages[] with page_number, job_id, status, url, error_message and retry_count."],
      ["GET /jobs/{id}/pages/{n}/status", "Page status by number."],
      ["GET /jobs/{id}/pages/{n}/result", "JSON with result.markdown for a completed page; available before the merge."],
      ["GET /jobs/{id}/pages/{n}/pdf", "JSON with a signed PDF url, expires_in=900 and expires_at; does not return PDF bytes."],
      ["POST /jobs/{id}/pages/{n}/retry", "Retries a failed page, up to 3 manual attempts; save the new page_job_id returned."],
    ],
    pagesNote: "Before splitting, /pages may return 404; during creation, pages[] may be incomplete and job_id may be null. Poll again. Failed pages block the merge until recovered. Every endpoint requires authentication and checks ownership.",
    pdfNote: "Open the signed url directly, without Authorization or X-API-Key. It lasts 15 minutes; request another after it expires and preserve its entire query string. Do not add URL parameters.",
    engineNote: "The server may route pages through execution engines when configured. Use the same endpoints; an engine upload parameter does not select presets or queues.",
    imagesIntro: "Florence-2 describes images or extracts text with regions (OCR). All four inference routes create a job and wait for its result in the same request. The default request budget is 60 seconds; the task may continue up to its 120-second limit, both configurable on the server.",
    imagesHead: ["Endpoint", "Input / output"],
    imagesRows: [
      ["POST /images/describe/upload", "multipart: file, optional task, tags, project/project_id and folder/folder_id. Returns description and task."],
      ["POST /images/describe", "JSON: image_base64, optional filename, task, tags as an array and location. Same description response."],
      ["POST /images/ocr/upload", "multipart: file, tags and location. Returns text and lines[]."],
      ["POST /images/ocr", "JSON: image_base64, optional filename, tags as an array and location. Same OCR; no task parameter."],
      ["GET /images/capabilities", "Worker state: dependencies_installed, model_downloaded, model_loaded, device_resolved and reason. Authenticated; does not start inference."],
    ],
    imageOptions: "PNG, JPEG, WEBP, BMP, GIF and TIFF, detected from their bytes. Default limits: 10 MB of decoded image data and 50 million pixels (VISION_MAX_IMAGE_SIZE_MB / VISION_MAX_IMAGE_PIXELS). Base64 accepts a data:image/...;base64, prefix and line breaks. Projects follow the same requirements as documents; repeated images create new jobs.",
    imageTasks: "task only accepts <CAPTION>, <DETAILED_CAPTION> and <MORE_DETAILED_CAPTION> (default, configurable via VISION_CAPTION_TASK). Arbitrary prompts are not accepted. In curl, use --form-string for these values: -F interprets < as reading a file.",
    imageResponse: "Success (200): job_id, status=completed, project, folder, image_base64 (echo of the original bytes), image_mime_type, image_bytes, image_sha256, width, height, model (model_id, revision, device, dtype) and duration_ms, plus the description or OCR. duration_ms is processing time reported by the worker, not total request time.",
    ocrNote: "Every line has text, quad_box=[x1,y1,x2,y2,x3,y3,x4,y4] and bbox=[x_min,y_min,x_max,y_max], in original image pixels. Images without text return 200 with empty text and lines=[]. The example below shows only OCR fields.",
    timeoutTitle: "Timeout and current limitations",
    timeout: "A 504 VISION_TIMEOUT includes detail.job_id, poll_url and result_url; the task continues. Poll poll_url for status and avoid automatically uploading again. Current limitation: /jobs/{id}/result requires Markdown, but the vision payload has no such field; recovery after completion may fail with 500. Save the successful response from the image request itself.",
    retention: "Vision results live in Redis for RESULT_TTL_SECONDS (1 hour by default), without Elasticsearch/MinIO persistence. The worker deletes the temporary image. Success status is not updated in MySQL; once the cache expires, the job list may revert to queued.",
    imageErrors: "Vision errors generally use detail={error_code,message,job_id}; authentication and validation errors may differ. 413: size; 422: invalid base64, format, task, pixels or location; 503: vision disabled, unavailable worker/model or no engine capacity (VISION_ENGINE_UNAVAILABLE, with Retry-After). /capabilities also returns 503 when vision is disabled.",
  },
};

function MediaSections({ lang }: { lang: Lang }) {
  const t = MEDIA_COPY[lang];
  const pt = lang === "pt";
  const block = (code: string) => <CodeBlock code={code} copyLabel={COPY[lang].copy} />;
  const key = pt ? "SUA_CHAVE" : "YOUR_KEY";
  const project = pt ? "Documentos" : "Documents";
  const curl = (path: string, fields: string[], method = "POST") =>
    [`curl -X ${method} "${API_URL}${path}"`, `  -H "X-API-Key: ${key}"`, ...fields]
      .join(" \\\n");

  return (
    <>
      <Section id="documentos" title={COPY[lang].sections.documents}>
        <Endpoint method="POST" path="/upload" />
        <Endpoint method="POST" path="/convert" />
        <P>{t.docsIntro}</P>
        <Table head={t.fields} rows={t.docsRows} />
        <H3>{t.presetsTitle}</H3>
        <Table head={t.presetsHead} rows={t.presets} />
        <P small>{t.formats}</P>
        <H3>{t.example}</H3>
        {block(curl("/upload", [`  -F "file=@${pt ? "relatorio" : "report"}.pdf"`, `  -F "project=${project}"`, `  -F "folder=${pt ? "Contratos" : "Contracts"}"`, '  -F "docling_preset=quality"', '  -F "tags=pdf,ocr"']))}
        {block(curl("/convert", ['  -F "source_type=url"', '  -F "source=https://example.com/document.pdf"', `  -F "project=${project}"`]))}
        <P small>{t.docsDuplicate}</P>
        <P>{t.docsResult}</P>
        {block(curl(`/jobs/${EXAMPLE_JOB_ID}/result`, [], "GET"))}
        <H3>{t.resultExample}</H3>
        {block(JSON.stringify({ job_id: EXAMPLE_JOB_ID, type: "main", status: "completed", result: { markdown: "# Document\n\nContent...", metadata: { pages: 2, words: 120, format: "pdf", size_bytes: 0 } }, completed_at: "2026-10-05T12:00:00" }, null, 2))}
      </Section>

      <Section id="paginas-pdf" title={COPY[lang].sections.pages}>
        <P>{t.pagesIntro}</P>
        <Table head={t.pagesHead} rows={t.pagesRows} />
        <P small>{t.pagesNote}</P>
        {block(curl(`/jobs/${EXAMPLE_JOB_ID}/pages`, [], "GET"))}
        {block(curl(`/jobs/${EXAMPLE_JOB_ID}/pages/1/result`, [], "GET"))}
        {block(curl(`/jobs/${EXAMPLE_JOB_ID}/pages/1/pdf`, [], "GET"))}
        <P small>{t.pdfNote}</P>
        {block(curl(`/jobs/${EXAMPLE_JOB_ID}/pages/1/retry`, []))}
        <P small>{t.engineNote}</P>
      </Section>

      <Section id="imagens" title={COPY[lang].sections.images}>
        <P>{t.imagesIntro}</P>
        <Table head={t.imagesHead} rows={t.imagesRows} />
        <P small>{t.imageOptions}</P>
        <P small>{t.imageTasks}</P>
        <H3>{t.example}</H3>
        {block(curl("/images/describe/upload", ['  -F "file=@photo.jpg"', `  -F "project=${project}"`, '  --form-string "task=<CAPTION>"']))}
        {block(curl("/images/ocr/upload", ['  -F "file=@receipt.png"', `  -F "project=${project}"`, '  -F "tags=ocr"']))}
        {block(`import base64\nimport requests\n\nwith open("receipt.png", "rb") as f:\n    image = base64.b64encode(f.read()).decode("ascii")\n\nr = requests.post(\n    "${API_URL}/images/ocr",\n    headers={"X-API-Key": "${key}"},\n    json={"image_base64": image, "filename": "receipt.png",\n          "project": "${project}", "tags": ["ocr"]},\n    timeout=75,\n)\nr.raise_for_status()\nprint(r.json()["text"])`)}
        <P>{t.imageResponse}</P>
        <P small>{t.ocrNote}</P>
        {block(JSON.stringify({ text: "TOTAL 42.00", lines: [{ text: "TOTAL 42.00", quad_box: [12, 20, 180, 20, 180, 40, 12, 40], bbox: [12, 20, 180, 40] }] }, null, 2))}
        <H3>{t.timeoutTitle}</H3>
        <P>{t.timeout}</P>
        {block(JSON.stringify({ detail: { error_code: "VISION_TIMEOUT", message: "O job continua processando.", job_id: EXAMPLE_JOB_ID, poll_url: `/jobs/${EXAMPLE_JOB_ID}`, result_url: `/jobs/${EXAMPLE_JOB_ID}/result` } }, null, 2))}
        <P small>{t.retention}</P>
        <P small>{t.imageErrors}</P>
        {block(curl("/images/capabilities", [], "GET"))}
      </Section>
    </>
  );
}

const LIVE_CAPTURE_COPY = {
  pt: {
    title: "Microfone ao vivo",
    intro: "Transmita áudio pelo microfone e receba legendas enquanto fala. A página /live permite escolher projeto e pasta, iniciar a captura, finalizar para salvar ou cancelar a sessão. Requer HTTPS ou localhost e permissão para usar o microfone.",
    availability: "Piloto opt-in, desabilitado por padrão. Depende da ativação pelo operador e de capacidade GPU disponível. A validação de qualidade e os critérios para produção ainda estão pendentes; os tempos medidos no piloto não são uma garantia de latência.",
    open: "Abrir captura de microfone",
    api: "Integração pela API",
    auth: "Crie a sessão com JWT ou API key e informe o projeto, como nos uploads. O retorno contém job_id, ws_url e um ticket de uso único válido por 60 segundos. Conecte à ws_url retornada e envie o ticket no primeiro frame JSON, sem colocá-lo na URL.",
    capture: "Espere session.ready antes de enviar áudio. O formato é PCM s16le, mono, 16 kHz. Cada bloco de 200 ms contém 3.200 amostras (6.400 bytes), precedidas por um cabeçalho little-endian de 12 bytes: seq uint32 e offset_samples uint64, ambos iniciando em zero. Avance seq por bloco e offset_samples pelas amostras enviadas. A cauda pode ser menor; o máximo por bloco é 500 ms.",
    events: "Eventos e encerramento",
    head: ["Evento / ação", "Comportamento"],
    rows: [
      ["transcript.partial", "Substitua o texto provisório pela revisão mais recente; não concatene revisões."],
      ["transcript.final", "Acrescente o segmento confirmado uma vez, em ordem de segment_id. Ele não será alterado."],
      ["finish", "Envie a cauda do áudio e depois finish com last_seq. Continue lendo até session.completed."],
      ["session.completed", "O resultado foi salvo. Use /jobs/{job_id}/result?format=txt|json|vtt|srt ou abra a página do job."],
      ["cancel / DELETE", "Encerra a sessão e descarta os parciais. Uma queda de conexão exige uma nova sessão."],
    ],
    limits: "Limites padrão: uma sessão simultânea por worker, até 30 minutos por sessão e 2 segundos de backlog. Falta de capacidade retorna 503 com Retry-After; não há fila de arquivos nem retry automático do áudio. LIVE_DISABLED indica piloto desligado; LIVE_NOT_READY, serviço ainda indisponível; LIVE_CAPACITY_FULL, capacidade ocupada.",
    privacy: "O áudio original não é armazenado. Ao finalizar, o texto e os formatos de legenda ficam no projeto, com acesso restrito ao dono. Finalizar espera a persistência; fechar a conexão não salva um resultado concluído.",
  },
  en: {
    title: "Live microphone",
    intro: "Stream microphone audio and receive captions as you speak. The /live page lets you choose a project and folder, start capture, finish to save or cancel the session. HTTPS or localhost and microphone permission are required.",
    availability: "Opt-in pilot, disabled by default. An operator must enable it and GPU capacity must be available. Quality validation and production criteria are still pending; pilot timings are not a latency guarantee.",
    open: "Open microphone capture",
    api: "API integration",
    auth: "Create a session with a JWT or API key and specify its project, as for uploads. The response includes job_id, ws_url and a single-use ticket valid for 60 seconds. Connect to the returned ws_url and send the ticket in the first JSON frame, without putting it in the URL.",
    capture: "Wait for session.ready before sending audio. Use mono 16 kHz PCM s16le. Each 200 ms block contains 3,200 samples (6,400 bytes), preceded by a 12-byte little-endian header: seq uint32 and offset_samples uint64, both starting at zero. Increment seq per block and offset_samples by the samples sent. The tail may be shorter; the maximum block is 500 ms.",
    events: "Events and completion",
    head: ["Event / action", "Behavior"],
    rows: [
      ["transcript.partial", "Replace provisional text with the latest revision; do not concatenate revisions."],
      ["transcript.final", "Append each confirmed segment once, in segment_id order. It will not change."],
      ["finish", "Send the audio tail, then finish with last_seq. Keep reading until session.completed."],
      ["session.completed", "The result has been saved. Use /jobs/{job_id}/result?format=txt|json|vtt|srt or open the job page."],
      ["cancel / DELETE", "Ends the session and discards partial captions. A disconnected session requires a new session."],
    ],
    limits: "Default limits: one concurrent session per worker, up to 30 minutes per session and 2 seconds of backlog. Unavailable capacity returns 503 with Retry-After; there is no file queue or automatic audio retry. LIVE_DISABLED means the pilot is off; LIVE_NOT_READY means the service is unavailable; LIVE_CAPACITY_FULL means capacity is occupied.",
    privacy: "The original audio is not stored. Finishing saves the text and caption formats in the project, accessible only to its owner. Finish waits for persistence; closing the connection does not save a completed result.",
  },
};

function LiveCaptureDocs({ lang, copyLabel }: { lang: Lang; copyLabel: string }) {
  const t = LIVE_CAPTURE_COPY[lang];
  const key = lang === "pt" ? "SUA_API_KEY" : "YOUR_API_KEY";
  const body = JSON.stringify({ project: lang === "pt" ? "Aulas" : "Classes", name: lang === "pt" ? "Transcrição ao vivo" : "Live transcript", language: "pt" });
  const create = `curl --fail -X POST "${API_URL}/transcribe/live/sessions" \\
  -H "X-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  --data '${body}'`;
  return (
    <Section id="microfone-live" title={t.title}>
      <P>{t.intro}</P>
      <P><A href="/live">{t.open}</A></P>
      <P small>{t.availability}</P>
      <P>{lang === "pt" ? "Idioma do piloto: Português." : "Pilot language: Portuguese."}</P>
      <H3>{t.api}</H3>
      <Endpoint method="POST" path="/transcribe/live/sessions" />
      <Endpoint method="GET" path="/transcribe/live/sessions/{job_id}" />
      <Endpoint method="DELETE" path="/transcribe/live/sessions/{job_id}" />
      <P>{t.auth}</P>
      <CodeBlock code={create} copyLabel={copyLabel} />
      <Endpoint method="WS" path="/transcribe/live/sessions/{job_id}/stream" />
      <CodeBlock code={'{"type":"authenticate","protocol":1,"ticket":"<ticket>"}'} copyLabel={copyLabel} />
      <P>{t.capture}</P>
      <H3>{t.events}</H3>
      <Table head={t.head} rows={t.rows} />
      <CodeBlock code={'{"type":"finish","last_seq":149}\n{"type":"cancel"}'} copyLabel={copyLabel} />
      <P small>{lang === "pt" ? "As mensagens acima são alternativas. last_seq deve ser a última sequência enviada na sua sessão." : "The messages above are alternatives. last_seq must be the last sequence sent in your session."}</P>
      <P>{t.limits}</P>
      <P>{t.privacy}</P>
    </Section>
  );
}

const COMPUTE_COPY = {
  pt: {
    title: "Compute: execução e capacidade",
    intro: "Compute reúne os motores que executam os jobs, sua capacidade e as rotas por funcionalidade. A instalação padrão usa os workers locais; contas Modal são opcionais e atendem transcrição de arquivos.",
    admin: "As telas abaixo exigem usuário admin e são somente leitura. Elas mostram o estado e os comandos para o operador alterar a configuração. A API verifica a permissão de admin em cada operação.",
    head: ["Tela", "O que mostra"],
    engines: "Motores local/Modal, saúde, status, capacidade, teste, deploy e orçamento.",
    gpus: "GPUs declaradas e detectadas, VRAM orçada e uso atual. Valor desconhecido não significa zero.",
    routing: "Prioridade dos motores e backlog por funcionalidade. Sem rota, o job usa a fila local habitual.",
    status: "Despachante, worker remoto, tentativas em voo e workers configurados × vivos.",
    capacity: "Capacidade = workers × execuções por worker. A declaração não cria réplicas nem escolhe a placa CUDA do container. GPU local e Modal aceitam uma execução por worker; aumentar réplicas exige memória suficiente para todos os modelos na mesma placa.",
    health: "Um worker vivo pode estar ocupado ou com modelo ainda frio. A tela compara workers configurados e vivos; a confirmação de dispositivo e aquecimento vem dos logs e resultados. /health verifica a aplicação, enquanto o status Compute detalha a execução.",
    privacy: "Provider e motor são configurações distintas: faster-whisper/openai-whisper processam no worker; openai-api envia o áudio à OpenAI. O rótulo local informa qual executor atendeu. O orçamento Compute cobre contas Modal; cobranças de openai-api ficam fora dele. PDF e imagem têm rotas somente locais no adapter atual.",
    security: "Leituras HTTP aceitam JWT ou API key de admin; alterações exigem sessão JWT de admin. Credenciais Modal são somente escrita, seladas na API e abertas pelo worker remoto. Pausar um motor impede novas colocações; os trabalhos em voo terminam.",
    guide: "Setup, chaves, limites, deploy e benchmark no guia do operador",
    samples: "Leituras de diagnóstico (substitua o token JWT de admin)",
    fileCaptions: "Legendas parciais de arquivos acompanham um upload já enviado. A captura contínua de microfone foi implementada como piloto opt-in, com worker GPU próprio e ativação separada. Ela permanece desabilitada por padrão, com critérios de produção pendentes.",
  },
  en: {
    title: "Compute: execution and capacity",
    intro: "Compute brings together job execution engines, their capacity and per-feature routes. The default installation uses local workers; optional Modal accounts handle file transcription.",
    admin: "The screens below require an admin user and are read-only. They show state and commands operators can run to change configuration. The API checks admin permission for each operation.",
    head: ["Screen", "What it shows"],
    engines: "Local/Modal engines, health, status, capacity, tests, deployment and budget.",
    gpus: "Declared and detected GPUs, budgeted VRAM and current usage. An unknown value does not mean zero.",
    routing: "Engine priority and backlog per feature. Without a route, a job uses the usual local queue.",
    status: "Dispatcher, remote worker, in-flight attempts and configured versus live workers.",
    capacity: "Capacity = workers × executions per worker. Declaring capacity does not create replicas or select the container's CUDA device. Local GPU and Modal bindings accept one execution per worker; adding replicas requires enough memory for all models sharing the card.",
    health: "A live worker may be busy or have a cold model. The screen compares configured and live workers; logs and results confirm the device and model warmup. /health checks the application, while Compute status details execution.",
    privacy: "Providers and engines are separate settings: faster-whisper/openai-whisper process on the worker; openai-api sends audio to OpenAI. The local label identifies the executor. Compute budgets cover Modal accounts; openai-api charges are outside those budgets. The current adapter supports only local routes for PDFs and images.",
    security: "HTTP reads accept an admin JWT or API key; changes require an admin JWT session. Modal credentials are write-only, sealed by the API and opened by the remote worker. Pausing an engine blocks new placements; in-flight work finishes.",
    guide: "Setup, keys, limits, deployment and benchmarks in the operator guide",
    samples: "Diagnostic reads (replace the admin JWT token)",
    fileCaptions: "File captions follow an upload that has already been sent. Continuous microphone capture is implemented as an opt-in pilot with a separate GPU worker and activation. It remains disabled by default, with production criteria pending.",
  },
};

function ComputeDocs({ lang, copyLabel }: { lang: Lang; copyLabel: string }) {
  const t = COMPUTE_COPY[lang];
  const token = lang === "pt" ? "SEU_TOKEN_JWT_ADMIN" : "YOUR_ADMIN_JWT_TOKEN";
  const diagnostic = `curl --fail "${API_URL}/admin/engines/status" \\
  -H "Authorization: Bearer ${token}"

curl --fail "${API_URL}/admin/gpus" \\
  -H "Authorization: Bearer ${token}"`;

  return (
    <Section id="compute" title={t.title}>
      <P>{t.intro}</P>
      <P>{t.admin}</P>
      <Table
        head={t.head}
        rows={[
          [<A key="engines" href="/admin/engines">/admin/engines</A>, t.engines],
          [<A key="gpus" href="/admin/gpus">/admin/gpus</A>, t.gpus],
          [<A key="routing" href="/admin/routing">/admin/routing</A>, t.routing],
          [<A key="status" href="/admin/status">/admin/status</A>, t.status],
        ]}
      />
      <P>{t.capacity}</P>
      <P>{t.health}</P>
      <P>{t.privacy}</P>
      <P>{t.security}</P>
      <H3>{t.samples}</H3>
      <Endpoint method="GET" path="/admin/engines/status" />
      <Endpoint method="GET" path="/admin/gpus" />
      <CodeBlock code={diagnostic} copyLabel={copyLabel} />
      <P small>{t.fileCaptions}</P>
      <P><A href="https://github.com/geda-valentim/ingestify-to-ai/blob/main/docs/features/engines.md">{t.guide}</A></P>
    </Section>
  );
}

export default function DocsPage() {
  const [lang, setLang] = useState<Lang>("pt");

  useEffect(() => {
    setLang(detectLang());
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang === "pt" ? "pt-BR" : "en";
  }, [lang]);

  const chooseLang = (value: Lang) => {
    setLang(value);
    try {
      localStorage.setItem(LANG_STORAGE_KEY, value);
    } catch {
      // Not persisted; the choice still applies to this visit.
    }
    const url = new URL(window.location.href);
    url.searchParams.set("lang", value);
    window.history.replaceState(null, "", url);
  };

  const t = COPY[lang];
  const code = samples(lang);
  const block = (c: string) => <CodeBlock code={c} copyLabel={t.copy} />;

  const sections = [
    { id: "introducao", label: t.sections.intro },
    { id: "autenticacao", label: t.sections.auth },
    { id: "projetos", label: t.sections.projects },
    { id: "documentos", label: t.sections.documents },
    { id: "paginas-pdf", label: t.sections.pages },
    { id: "imagens", label: t.sections.images },
    { id: "compute", label: COMPUTE_COPY[lang].title },
    { id: "transcribe", label: t.sections.transcribe },
    { id: "transcribe-status", label: t.sections.status },
    { id: "transcribe-live", label: t.sections.live },
    { id: "microfone-live", label: LIVE_CAPTURE_COPY[lang].title },
    { id: "transcribe-result", label: t.sections.result },
    { id: "transcribe-erros", label: t.sections.errors },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      <AppHeader className="sticky top-0 z-10" />

      <div className="container mx-auto px-4 py-8">
        <div className="flex flex-col gap-8 lg:flex-row">
          {/* Sidebar */}
          <aside className="lg:w-64 lg:shrink-0">
            <nav className="lg:sticky lg:top-24 space-y-1 text-sm">
              <div className="flex gap-1 px-2 pb-4" role="group" aria-label="Idioma / Language">
                {LANGS.map(({ value, label }) => (
                  <Button
                    key={value}
                    type="button"
                    size="sm"
                    variant={lang === value ? "secondary" : "ghost"}
                    aria-pressed={lang === value}
                    onClick={() => chooseLang(value)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
              <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t.sidebarTitle}
              </p>
              {sections.map((s) => (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className="block rounded-md px-2 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  {s.label}
                </a>
              ))}
              <p className="px-2 pt-4 text-xs text-muted-foreground">{t.comingSoon}</p>
            </nav>
          </aside>

          {/* Content */}
          <main className="min-w-0 max-w-3xl flex-1 space-y-12">
            <Section id="introducao" title={t.sections.intro}>
              {t.intro}
              <Table rows={t.introRows} />
            </Section>

            <Section id="autenticacao" title={t.sections.auth}>
              {t.authIntro}
              <Table head={t.authHead} rows={t.authRows} />
              {t.authNote}
            </Section>

            <Section id="projetos" title={t.sections.projects}>
              {t.projectsIntro}
              <Table head={t.projectsHead} rows={t.projectsRows} />
              {t.projectsResolution}
              <H3>{t.projectsRequiredTitle}</H3>
              {block(RESPONSES.projectRequired)}
              {t.projectsNormalization}
              {t.projectsPrecedence}
              <H3>{t.projectsExampleTitle}</H3>
              {block(code.curlProject)}
            </Section>

            <MediaSections lang={lang} />

            <ComputeDocs lang={lang} copyLabel={t.copy} />

            <Section id="transcribe" title={t.sections.transcribe}>
              <Endpoint method="POST" path="/transcribe" />
              {t.transcribeIntro}

              <H3>{t.paramsTitle}</H3>
              <Table head={t.paramsHead} rows={t.paramsRows} />

              <H3>{t.filesTitle}</H3>
              <Table head={t.filesHead} rows={t.filesRows} />
              {t.filesNote}

              <H3>{t.exampleTitle}</H3>
              <Tabs defaultValue="curl">
                <TabsList>
                  <TabsTrigger value="curl">curl</TabsTrigger>
                  <TabsTrigger value="python">Python</TabsTrigger>
                  <TabsTrigger value="javascript">JavaScript</TabsTrigger>
                </TabsList>
                <TabsContent value="curl">
                  {block(code.curlCreate)}
                </TabsContent>
                <TabsContent value="python">
                  {block(code.python)}
                </TabsContent>
                <TabsContent value="javascript">
                  {block(code.javascript)}
                </TabsContent>
              </Tabs>

              <H3>{t.responseTitle}</H3>
              {block(RESPONSES.create)}
              <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">{t.duplicate}</div>
            </Section>

            <Section id="transcribe-status" title={t.sections.status}>
              <Endpoint method="GET" path="/jobs/{job_id}" />
              {t.statusIntro}
              {block(code.curlStatus)}
              {block(RESPONSES.status)}
              {t.statusFields}
              {t.statusNote}
            </Section>

            <Section id="transcribe-live" title={t.sections.live}>
              <Endpoint method="GET" path="/jobs/{job_id}/transcript/partial?since=N" />
              {t.liveIntro}
              {block(code.curlLive)}
              {block(RESPONSES.live)}
            </Section>

            <LiveCaptureDocs lang={lang} copyLabel={t.copy} />

            <Section id="transcribe-result" title={t.sections.result}>
              <Endpoint method="GET" path="/jobs/{job_id}/result?format=…" />
              {t.resultIntro}
              {block(code.curlResult)}

              <Table
                head={t.formatsHead}
                rows={FORMAT_TYPES.map(([format, type]) => [
                  <C key="f">{format}</C>,
                  <C key="c">{type}</C>,
                  t.formatsDesc[format],
                ])}
              />

              <Tabs defaultValue="markdown">
                <TabsList className="flex-wrap h-auto">
                  {FORMAT_TYPES.map(([format]) => (
                    <TabsTrigger key={format} value={format}>
                      {format}
                    </TabsTrigger>
                  ))}
                </TabsList>
                <TabsContent value="markdown">
                  {block(RESPONSES.markdown)}
                  <p className="pt-2 text-sm text-muted-foreground">{t.deviceNote}</p>
                </TabsContent>
                <TabsContent value="vtt">
                  {block(RESPONSES.vtt)}
                </TabsContent>
                <TabsContent value="srt">
                  {block(RESPONSES.srt)}
                </TabsContent>
                <TabsContent value="txt">
                  {block(RESPONSES.txt)}
                </TabsContent>
                <TabsContent value="json">
                  {block(RESPONSES.json)}
                  <p className="pt-2 text-sm text-muted-foreground">{t.wordsNote}</p>
                </TabsContent>
              </Tabs>
            </Section>

            <Section id="transcribe-erros" title={t.sections.errors}>
              {t.errorsIntro}
              <Table
                head={t.errorsHead}
                rows={Object.entries(t.errors).map(([status, when]) => [<C key="s">{status}</C>, when])}
              />
            </Section>
          </main>
        </div>
      </div>
    </div>
  );
}
