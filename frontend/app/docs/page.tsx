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
  "status": "completed",
  "progress": 100,
  "created_at": "2026-09-25T18:32:29",
  "started_at": "2026-09-25T18:32:38",
  "completed_at": "2026-09-25T18:33:28",
  "error": null,
  ...
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
    comingSoon: "Conversão de documentos, páginas e busca: em breve.",
    sections: {
      intro: "Introdução",
      auth: "Autenticação",
      projects: "Projetos e pastas",
      transcribe: "Transcrição de áudio e vídeo",
      status: "Acompanhar o job",
      result: "Baixar o resultado",
      errors: "Erros",
    },
    intro: (
      <P>
        A API do Ingestify é REST e assíncrona: você envia um arquivo, recebe um <C>job_id</C> na hora,
        acompanha o processamento e depois baixa o resultado.
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
        <C>metadata.device</C> diz onde a transcrição rodou: <C>cuda</C> (GPU), <C>cpu</C> ou <C>remote</C>{" "}
        (provedor externo).
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
    comingSoon: "Document conversion, pages and search: coming soon.",
    sections: {
      intro: "Introduction",
      auth: "Authentication",
      projects: "Projects and folders",
      transcribe: "Audio and video transcription",
      status: "Track the job",
      result: "Download the result",
      errors: "Errors",
    },
    intro: (
      <P>
        The Ingestify API is REST and asynchronous: you upload a file, get a <C>job_id</C> right away, track
        the processing and then download the result.
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
        <C>metadata.device</C> tells where the transcription ran: <C>cuda</C> (GPU), <C>cpu</C> or{" "}
        <C>remote</C> (external provider).
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
    { id: "transcribe", label: t.sections.transcribe },
    { id: "transcribe-status", label: t.sections.status },
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
              {t.statusNote}
            </Section>

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
