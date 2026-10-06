import Link from "next/link";
import { DOCS_API_URL as API_URL } from "./config";
import { CodeBlock } from "./code-block";
import { Badge } from "@/components/ui/badge";

import type { DocsLang as Lang } from "./topics";

// Real responses, captured from a run of the transcription flow on this stack.
const EXAMPLE_JOB_ID = "7186e44b-3098-4590-9b5f-a29e9991e4e7";
const EXAMPLE_PROJECT_ID = "3f2b9c1e-5a7d-4e8b-9c0a-1d2e3f4a5b6c";

function Endpoint({ method, path }: { method: string; path: string }) {
  return (
    <div className="flex items-center gap-2 font-mono text-sm">
      <Badge variant={method === "GET" ? "secondary" : "default"}>
        {method}
      </Badge>
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
                <th
                  key={h}
                  className="text-left font-medium px-3 py-2 whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={`align-top ${head || i > 0 ? "border-t" : ""}`}
            >
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

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {children}
    </section>
  );
}

function Subheading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-lg font-semibold pt-2">{children}</h2>;
}

function P({
  children,
  small,
}: {
  children: React.ReactNode;
  small?: boolean;
}) {
  return (
    <p
      className={
        small ? "text-sm text-muted-foreground" : "text-muted-foreground"
      }
    >
      {children}
    </p>
  );
}

function C({ children }: { children: React.ReactNode }) {
  return (
    <code className="bg-muted px-1.5 py-0.5 rounded text-[0.85em]">
      {children}
    </code>
  );
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
form.append("file", ${pt ? "arquivo" : "file"}); // ${pt ? 'um File/Blob, ex.: de um <input type="file">' : 'a File/Blob, e.g. from an <input type="file">'}
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
    comingSoon:
      "Consulte o Swagger para a referência completa, incluindo busca.",
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
        A API do Ingestify é REST e assíncrona: você envia um arquivo, recebe um{" "}
        <C>job_id</C> na hora, acompanha o processamento e depois baixa o
        resultado. As rotas de imagem esperam a inferência e devolvem descrição
        ou OCR na mesma requisição, com um prazo de espera.
      </P>
    ),
    introRows: [
      ["URL base", <C key="u">{API_URL}</C>],
      ["Formato", "JSON nas respostas; multipart/form-data nos uploads"],
      [
        "Idioma das mensagens",
        "As mensagens da API (message, detail) vêm em português",
      ],
      [
        "Referência completa",
        <A key="s" href={`${API_URL}/docs`}>
          {API_URL}/docs (Swagger)
        </A>,
      ],
    ],
    authIntro: (
      <P>Toda chamada precisa estar autenticada, de uma destas duas formas:</P>
    ),
    authHead: ["Header", "Quando usar"],
    authRows: [
      [
        <C key="k">X-API-Key: SUA_CHAVE</C>,
        <span key="d">
          Integrações e scripts. Crie a chave em{" "}
          <A href="/api-keys">API Keys</A>; ela só é exibida uma vez.
        </span>,
      ],
      [
        <C key="b">Authorization: Bearer TOKEN</C>,
        <span key="d">
          Sessão de usuário. O token vem de <C>POST /auth/login</C> (form com{" "}
          <C>username</C> e <C>password</C>) e expira.
        </span>,
      ],
    ],
    authNote: (
      <P small>
        Sem credencial válida a API responde <C>401</C>. Cada usuário só enxerga
        os próprios jobs: um <C>job_id</C> de outra pessoa responde <C>404</C>.
      </P>
    ),
    projectsIntro: (
      <P>
        Todo job pertence a exatamente um <strong>projeto</strong> seu e,
        opcionalmente, a uma <strong>pasta</strong> desse projeto (um nível só).
        O projeto é obrigatório em todo upload (<C>/upload</C>, <C>/convert</C>,{" "}
        <C>/transcribe</C>, <C>/images/…</C>); a pasta, não.
      </P>
    ),
    projectsHead: ["Campo", "Significado"],
    projectsRows: [
      [
        <C key="p">project</C>,
        "Nome do projeto. Se não existir, é criado (get-or-add).",
      ],
      [
        <C key="pi">project_id</C>,
        "ID de um projeto existente. Nunca cria. Não pode vir junto com project.",
      ],
      [
        <C key="f">folder</C>,
        "Nome da pasta dentro do projeto. Se não existir, é criada. Não pode conter “/”.",
      ],
      [
        <C key="fi">folder_id</C>,
        "ID de uma pasta existente; precisa ser do projeto do upload.",
      ],
    ],
    projectsResolution: (
      <P>
        O projeto vem do request (<C>project</C> ou <C>project_id</C>). Se o
        request não diz, vale o projeto vinculado à API key usada (veja{" "}
        <A href="/api-keys">API Keys</A>). Sem nenhum dos dois, a API responde{" "}
        <C>422</C> e nada é gravado:
      </P>
    ),
    projectsNormalization: (
      <P small>
        Nomes são comparados sem diferenciar maiúsculas, espaços repetidos e
        acentos sobre letras latinas: <C>reuniao SEMANAL</C> cai no projeto
        “Reunião Semanal”. Outros alfabetos não são alterados. Até 100
        caracteres.
      </P>
    ),
    projectsPrecedence: (
      <P small>
        Com <C>Authorization: Bearer</C> e <C>X-API-Key</C> no mesmo request,
        vale o token, e o projeto vinculado à key não é usado. Arquivos
        repetidos só são reaproveitados dentro do mesmo projeto: o mesmo arquivo
        enviado a outro projeto é processado de novo.
      </P>
    ),
    projectsExampleTitle: "Exemplos",
    projectsManagement: (
      <P>
        Em{" "}
        <a href="/projects" className="underline">
          Projects
        </a>
        , crie projetos e pastas, consulte contagens e volume dos arquivos,
        edite a descrição e arquive projetos. Em My Jobs, selecione jobs e use
        Move selected; no detalhe de um job, use Location → Move. Excluir uma
        pasta mantém os jobs na raiz do projeto. Só projetos vazios e sem API
        keys vinculadas podem ser excluídos. Nomes existentes aceitam correções
        de caixa, acentos e espaços.
      </P>
    ),
    projectsRequiredTitle: "Upload sem projeto — 422",
    transcribeIntro: (
      <P>
        Transcreve a fala de um áudio ou vídeo (Whisper). Do vídeo, só a faixa
        de áudio é usada. A resposta volta imediatamente com o <C>job_id</C>; a
        transcrição roda em segundo plano, na GPU quando disponível (com
        fallback automático para CPU). Todos os formatos de saída são gerados de
        uma vez: Markdown, legendas VTT e SRT, texto puro e JSON com segmentos.
      </P>
    ),
    paramsTitle: "Parâmetros (multipart/form-data)",
    paramsHead: ["Campo", "Tipo", "Padrão", "Descrição"],
    paramsRows: [
      [
        <C key="f">file</C>,
        "arquivo",
        <em key="r">obrigatório</em>,
        "O áudio ou vídeo.",
      ],
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
          <a
            href="/pt/docs/projects"
            className="text-primary underline-offset-4 hover:underline"
          >
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
      [
        <C key="n">name</C>,
        "texto",
        "nome do arquivo",
        "Nome para identificar o job na lista.",
      ],
      [
        <C key="tg">tags</C>,
        "texto",
        "nenhuma",
        <span key="d">
          Tags separadas por vírgula (<C>cliente-x, reunião</C>). Viram
          minúsculas; até 20 de até 50 caracteres. Filtre depois com{" "}
          <C>GET /jobs?tag=cliente-x</C>. Reenviar o mesmo arquivo adiciona as
          tags ao job existente.
        </span>,
      ],
      [
        <C key="l">language</C>,
        "texto",
        "detecção automática",
        <span key="d">
          Código ISO 639-1 do idioma falado (<C>pt</C>, <C>en</C>, <C>es</C>…).
          Informar melhora a precisão e evita erro de detecção em áudios curtos.
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
          Tempo de cada palavra (com <C>probability</C>) nos segmentos do
          formato <C>json</C>.
        </span>,
      ],
      [
        <C key="o">output_format</C>,
        "texto",
        <C key="v">markdown</C>,
        <span key="d">
          Formato devolvido por {JOB} quando você não passa <C>?format=</C>:{" "}
          <C>markdown</C>, <C>vtt</C>, <C>srt</C>, <C>txt</C> ou <C>json</C>. Os
          outros continuam disponíveis.
        </span>,
      ],
    ],
    filesTitle: "Arquivos aceitos",
    filesHead: ["Tipo", "Formatos", "Tamanho máximo"],
    filesRows: [
      ["Áudio", "MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC", "50 MB"],
      [
        "Vídeo",
        "MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP",
        "500 MB",
      ],
    ],
    filesNote: (
      <P small>
        O tipo é reconhecido pelo MIME type ou pela extensão. Os limites são
        configuráveis no servidor (<C>MAX_AUDIO_FILE_SIZE_MB</C>,{" "}
        <C>MAX_VIDEO_FILE_SIZE_MB</C>).
      </P>
    ),
    exampleTitle: "Exemplo completo",
    responseTitle: "Resposta — 200",
    duplicate: (
      <>
        <strong className="text-foreground">Arquivo repetido:</strong> se você
        já enviou exatamente o mesmo arquivo <em>para o mesmo projeto</em>,
        nenhum job novo é criado. A resposta traz o <C>job_id</C> do job
        existente (com <C>status: &quot;queued&quot;</C> e uma mensagem
        avisando). Consulte o status dele normalmente — pode já estar concluído.
        O <C>output_format</C> do novo envio passa a valer para esse job.
      </>
    ),
    statusIntro: (
      <P>
        Consulte a cada poucos segundos até <C>status</C> ser <C>completed</C>{" "}
        ou <C>failed</C>. Os estados possíveis são <C>queued</C>,{" "}
        <C>processing</C>, <C>completed</C> e <C>failed</C>; <C>progress</C> vai
        de 0 a 100 e, se falhar, <C>error</C> explica o motivo.
      </P>
    ),
    statusFields: (
      <P small>
        Durante a transcrição, <C>transcribed_seconds</C> de{" "}
        <C>media_duration</C> mostra até onde o áudio já foi transcrito, em
        segundos. Quando o servidor distribui o trabalho entre motores (a GPU
        local e contas na nuvem), o status também traz <C>engine.kind</C> (
        <C>local</C> ou <C>cloud</C>) e, enquanto espera, <C>queue_reason</C> (
        <C>in_queue</C>: aguardando vaga; <C>starting</C>: a GPU na nuvem está
        ligando). Sem esse roteamento configurado, os dois campos vêm{" "}
        <C>null</C>.
      </P>
    ),
    liveIntro: (
      <P>
        Enquanto um job está em <C>processing</C>, o texto já transcrito pode
        ser lido por trechos, sem esperar o fim. A resposta traz os segmentos a
        partir de <C>since</C> e, em <C>next</C>, o valor a passar na próxima
        consulta, para receber só o que é novo. Quando o job termina a lista
        fica vazia: o texto completo está em {JOB}.
      </P>
    ),
    statusNote: (
      <P small>
        Referência medida na GPU: um áudio de 10 segundos levou cerca de 1
        minuto na primeira transcrição (o worker carrega o modelo) e cerca de 10
        segundos nas seguintes, contando a fila. Consultar a cada 2–5 segundos é
        suficiente.
      </P>
    ),
    resultIntro: (
      <P>
        Sem <C>?format=</C>, vale o <C>output_format</C> escolhido no envio. Com
        ele, você pede qualquer formato a qualquer momento — todos foram
        gerados. Os formatos de arquivo vêm com <C>Content-Disposition</C> e
        podem ser salvos direto.
      </P>
    ),
    formatsHead: ["format", "Content-Type", "Conteúdo"],
    formatsDesc: {
      markdown:
        "Transcrição em Markdown + metadados (idioma, duração, device).",
      vtt: "Legenda WebVTT, pronta para <track> em HTML5.",
      srt: "Legenda SRT para players e editores de vídeo.",
      txt: "Só o texto, um segmento por linha.",
      json: "Texto, duração e segmentos com início/fim em segundos.",
    },
    deviceNote: (
      <>
        <C>metadata.device</C> diz onde a transcrição rodou: <C>cuda</C> (GPU
        deste servidor), <C>cpu</C>, <C>modal:L4</C> (GPU na nuvem, com o tipo
        da placa) ou <C>remote</C> (API externa).
      </>
    ),
    wordsNote: (
      <>
        Com <C>include_word_timestamps=true</C>, cada segmento ganha uma lista{" "}
        <C>words</C> com <C>word</C>, <C>start</C>, <C>end</C> e{" "}
        <C>probability</C>.
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
      "400":
        "Arquivo vazio; ou, em /result, o job ainda está em processamento.",
      "404":
        "Job, projeto ou pasta inexistente ou de outro usuário, ou formato pedido indisponível (ex.: ?format=vtt num job de documento).",
      "413": "Arquivo acima do limite de tamanho.",
      "422":
        "Formato de arquivo não suportado, output_format/format inválido, upload sem projeto, ou nome de projeto/pasta inválido.",
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
        The Ingestify API is REST and asynchronous: you upload a file, get a{" "}
        <C>job_id</C> right away, track the processing and then download the
        result. Image routes wait for inference and return a description or OCR
        in the same request, within a time budget.
      </P>
    ),
    introRows: [
      ["Base URL", <C key="u">{API_URL}</C>],
      ["Format", "JSON responses; multipart/form-data for uploads"],
      ["Message language", "API messages (message, detail) are in Portuguese"],
      [
        "Full reference",
        <A key="s" href={`${API_URL}/docs`}>
          {API_URL}/docs (Swagger)
        </A>,
      ],
    ],
    authIntro: <P>Every call must be authenticated, in one of two ways:</P>,
    authHead: ["Header", "When to use it"],
    authRows: [
      [
        <C key="k">X-API-Key: YOUR_KEY</C>,
        <span key="d">
          Integrations and scripts. Create the key under{" "}
          <A href="/api-keys">API Keys</A>; it is shown only once.
        </span>,
      ],
      [
        <C key="b">Authorization: Bearer TOKEN</C>,
        <span key="d">
          User sessions. The token comes from <C>POST /auth/login</C> (a form
          with <C>username</C> and <C>password</C>) and expires.
        </span>,
      ],
    ],
    authNote: (
      <P small>
        Without valid credentials the API answers <C>401</C>. Users only see
        their own jobs: another person&apos;s <C>job_id</C> answers <C>404</C>.
      </P>
    ),
    projectsIntro: (
      <P>
        Every job belongs to exactly one of your <strong>projects</strong> and,
        optionally, to a <strong>folder</strong> in that project (one level
        only). The project is required on every upload (<C>/upload</C>,{" "}
        <C>/convert</C>, <C>/transcribe</C>, <C>/images/…</C>); the folder is
        not.
      </P>
    ),
    projectsHead: ["Field", "Meaning"],
    projectsRows: [
      [
        <C key="p">project</C>,
        "Project name. Created if it does not exist (get-or-add).",
      ],
      [
        <C key="pi">project_id</C>,
        "ID of an existing project. Never creates. Not allowed together with project.",
      ],
      [
        <C key="f">folder</C>,
        "Folder name inside the project. Created if it does not exist. Cannot contain “/”.",
      ],
      [
        <C key="fi">folder_id</C>,
        "ID of an existing folder; it must belong to the upload's project.",
      ],
    ],
    projectsResolution: (
      <P>
        The project comes from the request (<C>project</C> or <C>project_id</C>
        ). When the request names none, the project bound to the API key is used
        (see <A href="/api-keys">API Keys</A>). With neither, the API answers{" "}
        <C>422</C> and nothing is stored:
      </P>
    ),
    projectsNormalization: (
      <P small>
        Names are matched ignoring case, repeated spaces and accents on Latin
        letters: <C>reuniao SEMANAL</C> lands in the “Reunião Semanal” project.
        Other scripts are left as they are. Up to 100 characters.
      </P>
    ),
    projectsPrecedence: (
      <P small>
        With both <C>Authorization: Bearer</C> and <C>X-API-Key</C> on one
        request, the token wins and the key&apos;s project is not used. Repeated
        files are only reused within the same project: the same file sent to
        another project is processed again.
      </P>
    ),
    projectsExampleTitle: "Examples",
    projectsManagement: (
      <P>
        In{" "}
        <a href="/projects" className="underline">
          Projects
        </a>
        , create projects and folders, view job counts and source volume, edit
        descriptions and archive projects. In My Jobs, select jobs and use Move
        selected; in a job detail, use Location → Move. Deleting a folder keeps
        its jobs in the project root. Only empty projects without linked API
        keys can be deleted. Existing names allow corrections to capitalization,
        accents and spacing.
      </P>
    ),
    projectsRequiredTitle: "Upload with no project — 422",
    transcribeIntro: (
      <P>
        Transcribes the speech in an audio or video file (Whisper). For video,
        only the audio track is used. The response comes back immediately with
        the <C>job_id</C>; the transcription runs in the background, on the GPU
        when available (falling back to CPU automatically). Every output format
        is produced at once: Markdown, VTT and SRT subtitles, plain text and
        JSON with segments.
      </P>
    ),
    paramsTitle: "Parameters (multipart/form-data)",
    paramsHead: ["Field", "Type", "Default", "Description"],
    paramsRows: [
      [
        <C key="f">file</C>,
        "file",
        <em key="r">required</em>,
        "The audio or video.",
      ],
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
          <a
            href="/docs/projects"
            className="text-primary underline-offset-4 hover:underline"
          >
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
      [
        <C key="n">name</C>,
        "string",
        "file name",
        "Name that identifies the job in your list.",
      ],
      [
        <C key="tg">tags</C>,
        "string",
        "none",
        <span key="d">
          Comma-separated tags (<C>client-x, meeting</C>). Lower-cased; up to 20
          of up to 50 characters. Filter later with{" "}
          <C>GET /jobs?tag=client-x</C>. Re-uploading the same file adds the
          tags to the existing job.
        </span>,
      ],
      [
        <C key="l">language</C>,
        "string",
        "auto-detected",
        <span key="d">
          ISO 639-1 code of the spoken language (<C>pt</C>, <C>en</C>, <C>es</C>
          …). Setting it improves accuracy and avoids misdetection on short
          clips.
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
          Timing for every word (with <C>probability</C>) in the segments of the{" "}
          <C>json</C> format.
        </span>,
      ],
      [
        <C key="o">output_format</C>,
        "string",
        <C key="v">markdown</C>,
        <span key="d">
          Format returned by {JOB} when you don&apos;t pass <C>?format=</C>:{" "}
          <C>markdown</C>, <C>vtt</C>, <C>srt</C>, <C>txt</C> or <C>json</C>.
          The others remain available.
        </span>,
      ],
    ],
    filesTitle: "Accepted files",
    filesHead: ["Type", "Formats", "Max size"],
    filesRows: [
      ["Audio", "MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC", "50 MB"],
      [
        "Video",
        "MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP",
        "500 MB",
      ],
    ],
    filesNote: (
      <P small>
        The type is recognised by MIME type or file extension. Limits are
        configurable on the server (<C>MAX_AUDIO_FILE_SIZE_MB</C>,{" "}
        <C>MAX_VIDEO_FILE_SIZE_MB</C>).
      </P>
    ),
    exampleTitle: "Full example",
    responseTitle: "Response — 200",
    duplicate: (
      <>
        <strong className="text-foreground">Repeated file:</strong> if you
        already uploaded the exact same file <em>to the same project</em>, no
        new job is created. The response carries the existing job&apos;s{" "}
        <C>job_id</C> (with <C>status: &quot;queued&quot;</C> and a message
        saying so). Check its status as usual — it may already be done. The{" "}
        <C>output_format</C> of the new request becomes that job&apos;s default.
      </>
    ),
    statusIntro: (
      <P>
        Poll every few seconds until <C>status</C> is <C>completed</C> or{" "}
        <C>failed</C>. The possible states are <C>queued</C>, <C>processing</C>,{" "}
        <C>completed</C> and <C>failed</C>; <C>progress</C> goes from 0 to 100
        and, on failure, <C>error</C> explains why.
      </P>
    ),
    statusFields: (
      <P small>
        While transcribing, <C>transcribed_seconds</C> of <C>media_duration</C>{" "}
        shows how far into the audio the transcription is, in seconds. When the
        server spreads work across engines (this server&apos;s GPU and cloud
        accounts), the status also carries <C>engine.kind</C> (<C>local</C> or{" "}
        <C>cloud</C>) and, while it waits, <C>queue_reason</C> (<C>in_queue</C>:
        waiting for a slot; <C>starting</C>: the cloud GPU is starting up).
        Without that routing configured, both fields are <C>null</C>.
      </P>
    ),
    liveIntro: (
      <P>
        While a job is <C>processing</C>, the text transcribed so far can be
        read in pieces, without waiting for the end. The response carries the
        segments from <C>since</C> on and, in <C>next</C>, the value to pass on
        the next call so you only get what is new. Once the job finishes the
        list is empty: the full text is at {JOB}.
      </P>
    ),
    statusNote: (
      <P small>
        Measured on the GPU: a 10-second clip took about 1 minute on the first
        transcription (the worker loads the model) and about 10 seconds
        afterwards, queue included. Polling every 2–5 seconds is enough.
      </P>
    ),
    resultIntro: (
      <P>
        Without <C>?format=</C>, the <C>output_format</C> chosen at upload
        applies. With it, you can ask for any format at any time — all of them
        were produced. File formats come with <C>Content-Disposition</C> and can
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
        <C>metadata.device</C> tells where the transcription ran: <C>cuda</C>{" "}
        (this server&apos;s GPU), <C>cpu</C>, <C>modal:L4</C> (a cloud GPU, with
        the card type) or <C>remote</C> (an external API).
      </>
    ),
    wordsNote: (
      <>
        With <C>include_word_timestamps=true</C>, every segment gets a{" "}
        <C>words</C> list with <C>word</C>, <C>start</C>, <C>end</C> and{" "}
        <C>probability</C>.
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
      "404":
        "Job, project or folder doesn't exist or belongs to another user, or the requested format isn't available (e.g. ?format=vtt on a document job).",
      "413": "File above the size limit.",
      "422":
        "Unsupported file type, invalid output_format/format, an upload with no project, or an invalid project/folder name.",
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
    docsIntro:
      "Converte PDFs e documentos em Markdown com Docling. /upload recebe um arquivo e devolve job_id imediatamente. /convert também recebe fontes externas; ambos usam multipart/form-data.",
    fields: ["Campo", "Uso"],
    docsRows: [
      [
        "file",
        "Obrigatório no /upload; no /convert quando source_type=file. Até 50 MB por padrão (MAX_FILE_SIZE_MB).",
      ],
      [
        "project / project_id",
        "Projeto obrigatório, salvo API key vinculada. folder / folder_id são opcionais; veja Projetos e pastas.",
      ],
      [
        "name / tags",
        "Nome opcional e tags separadas por vírgula. O padrão de name é o nome do arquivo.",
      ],
      [
        "docling_preset",
        "Apenas /upload: fast (padrão), balanced ou quality. /convert usa as opções DOCLING_* do servidor.",
      ],
      [
        "source_type / source",
        "No /convert: file + file; url + URL pública HTTP(S); gdrive + ID; dropbox + caminho.",
      ],
      [
        "X-Source-Token",
        "Header obrigatório para gdrive e dropbox: token do provedor, separado da autenticação do Ingestify.",
      ],
    ],
    presetsTitle: "Escolher velocidade e OCR",
    presetsHead: ["Preset", "OCR", "Imagens", "Tabelas", "Uso"],
    presets: [
      ["fast", "não", "não", "sim", "PDF digital"],
      ["balanced", "não", "sim", "sim", "PDF com figuras"],
      ["quality", "sim", "sim", "sim", "PDF escaneado; mais lento"],
    ],
    formats:
      "PDF, DOCX, HTML, PPTX e XLSX dependem do suporte da versão instalada do Docling. A API aceita o upload antes de validar a conversão: um arquivo incompatível termina com status failed. DOC/PPT/XLS legados, RTF e ODT não têm sucesso garantido.",
    docsDuplicate:
      "O mesmo arquivo no mesmo projeto reaproveita um job que não esteja failed e adiciona as tags. A pasta do job existente é preservada; trocar o preset no reenvio não força outra conversão. Um arquivo em outro projeto é processado novamente.",
    docsResult:
      "Consulte /jobs/{job_id} a cada poucos segundos e leia result.markdown de /jobs/{job_id}/result quando completed. Documentos não geram VTT/SRT. /result retorna 400 enquanto o job processa, 500 se falhou e 404 se o status/resultado expirou.",
    example: "Exemplos de requisição",
    resultExample: "Exemplo ilustrativo de resultado",
    pagesIntro:
      "PDFs com duas ou mais páginas são divididos e convertidos em paralelo; o Markdown final reúne as páginas em ordem. Use o ID principal e números de página começando em 1. Um PDF de uma página é convertido inteiro e não tem jobs de página.",
    pagesHead: ["Endpoint", "Uso"],
    pagesRows: [
      [
        "GET /jobs/{id}/pages",
        "Lista total_pages, pages_completed, pages_failed e pages[] com page_number, job_id, status, url, error_message e retry_count.",
      ],
      ["GET /jobs/{id}/pages/{n}/status", "Status de uma página pelo número."],
      [
        "GET /jobs/{id}/pages/{n}/result",
        "JSON com result.markdown de uma página concluída; não precisa aguardar o merge.",
      ],
      [
        "GET /jobs/{id}/pages/{n}/pdf",
        "JSON com url assinada do PDF, expires_in=900 e expires_at; não devolve os bytes do PDF.",
      ],
      [
        "POST /jobs/{id}/pages/{n}/retry",
        "Reprocessa uma página failed, até 3 tentativas manuais; guarde o novo page_job_id retornado.",
      ],
    ],
    pagesNote:
      "Antes do split, /pages pode responder 404; durante a criação, pages[] pode estar incompleto e job_id pode ser null. Consulte novamente. Páginas failed bloqueiam o merge até serem recuperadas. Todos os endpoints exigem autenticação e verificam o dono.",
    pdfNote:
      "Abra a url assinada diretamente, sem Authorization ou X-API-Key. Ela vale por 15 minutos; peça outra quando expirar e preserve toda a query string. Não acrescente parâmetros à URL.",
    engineNote:
      "O servidor pode rotear páginas por motores de execução quando configurado. Você continua usando os mesmos endpoints; presets e filas não são escolhidos por um parâmetro engine no upload.",
    imagesIntro:
      "Florence-2 descreve imagens ou extrai texto com regiões (OCR). As quatro rotas de inferência criam um job e esperam o resultado na mesma requisição. O prazo padrão é 60 segundos; a task pode continuar até o seu limite de 120 segundos, configuráveis no servidor.",
    imagesHead: ["Endpoint", "Entrada / saída"],
    imagesRows: [
      [
        "POST /images/describe/upload",
        "multipart: file, task opcional, tags, project/project_id e folder/folder_id. Retorna description e task.",
      ],
      [
        "POST /images/describe",
        "JSON: image_base64, filename opcional, task, tags como lista e localização. Mesma resposta de descrição.",
      ],
      [
        "POST /images/ocr/upload",
        "multipart: file, tags e localização. Retorna text e lines[].",
      ],
      [
        "POST /images/ocr",
        "JSON: image_base64, filename opcional, tags como lista e localização. Mesmo OCR; não recebe task.",
      ],
      [
        "GET /images/capabilities",
        "Estado do worker: dependencies_installed, model_downloaded, model_loaded, device_resolved e reason. Exige autenticação; não inicia inferência.",
      ],
    ],
    imageOptions:
      "PNG, JPEG, WEBP, BMP, GIF e TIFF, detectados pelos bytes. Limite padrão: 10 MB de imagem decodificada e 50 milhões de pixels (VISION_MAX_IMAGE_SIZE_MB / VISION_MAX_IMAGE_PIXELS). Base64 aceita prefixo data:image/...;base64, e quebras de linha. O projeto é obrigatório pelas mesmas regras dos documentos; imagem repetida cria outro job.",
    imageTasks:
      "task aceita apenas <CAPTION>, <DETAILED_CAPTION> e <MORE_DETAILED_CAPTION> (padrão, configurável por VISION_CAPTION_TASK). Não aceita um prompt livre. Em curl, use --form-string para esses valores: -F interpreta o caractere < como leitura de arquivo.",
    imageResponse:
      "Sucesso (200): job_id, status=completed, project, folder, image_base64 (eco dos bytes originais), image_mime_type, image_bytes, image_sha256, width, height, model (model_id, revision, device, dtype) e duration_ms, além da descrição ou do OCR. duration_ms mede o processamento reportado pelo worker; não é o tempo total da requisição.",
    ocrNote:
      "Cada linha tem text, quad_box=[x1,y1,x2,y2,x3,y3,x4,y4] e bbox=[x_min,y_min,x_max,y_max], em pixels da imagem original. Imagem sem texto retorna 200, text vazio e lines=[]. O exemplo abaixo mostra apenas os campos de OCR.",
    timeoutTitle: "Timeout e limites atuais",
    timeout:
      "Um 504 VISION_TIMEOUT traz detail.job_id, poll_url e result_url; a task continua. Consulte poll_url para o status e evite reenviar automaticamente. Limitação atual: /jobs/{id}/result exige Markdown, mas o resultado de visão não tem esse campo; após completar, essa recuperação pode falhar com 500. Salve a resposta de sucesso da própria chamada de imagem.",
    retention:
      "O resultado de visão fica no Redis por RESULT_TTL_SECONDS (1 hora por padrão), sem persistência em Elasticsearch/MinIO. A imagem temporária é apagada pelo worker. O status de sucesso não é atualizado no MySQL; após expirar o cache, a listagem pode voltar a queued.",
    imageErrors:
      "Erros de visão geralmente usam detail={error_code,message,job_id}; erros de autenticação e validação podem ter outro formato. 413: tamanho; 422: base64, formato, task, pixels ou localização inválidos; 503: visão desabilitada, worker/modelo indisponível ou motor sem vaga (VISION_ENGINE_UNAVAILABLE, com Retry-After). /capabilities também responde 503 se a visão estiver desabilitada.",
  },
  en: {
    docsIntro:
      "Converts PDFs and documents to Markdown with Docling. /upload accepts a file and immediately returns job_id. /convert also accepts external sources; both use multipart/form-data.",
    fields: ["Field", "Usage"],
    docsRows: [
      [
        "file",
        "Required on /upload; on /convert when source_type=file. Default limit: 50 MB (MAX_FILE_SIZE_MB).",
      ],
      [
        "project / project_id",
        "Required unless the API key is bound to a project. folder / folder_id are optional; see Projects and folders.",
      ],
      [
        "name / tags",
        "Optional display name and comma-separated tags. name defaults to the file name.",
      ],
      [
        "docling_preset",
        "/upload only: fast (default), balanced or quality. /convert uses the server's DOCLING_* settings.",
      ],
      [
        "source_type / source",
        "On /convert: file + file; url + public HTTP(S) URL; gdrive + ID; dropbox + path.",
      ],
      [
        "X-Source-Token",
        "Required header for gdrive and dropbox: the provider token, separate from Ingestify authentication.",
      ],
    ],
    presetsTitle: "Choosing speed and OCR",
    presetsHead: ["Preset", "OCR", "Images", "Tables", "Usage"],
    presets: [
      ["fast", "no", "no", "yes", "Digital PDF"],
      ["balanced", "no", "yes", "yes", "PDF with figures"],
      ["quality", "yes", "yes", "yes", "Scanned PDF; slower"],
    ],
    formats:
      "PDF, DOCX, HTML, PPTX and XLSX depend on the installed Docling version. The API accepts the upload before validating conversion: an incompatible file ends with status failed. Legacy DOC/PPT/XLS, RTF and ODT are not guaranteed to convert.",
    docsDuplicate:
      "The same file in the same project reuses a job that is not failed and adds the supplied tags. The existing job's folder is preserved; changing the preset on re-upload does not force conversion. Uploading to another project processes the file again.",
    docsResult:
      "Poll /jobs/{job_id} every few seconds and read result.markdown from /jobs/{job_id}/result once completed. Documents do not produce VTT/SRT. /result returns 400 while processing, 500 on failure and 404 if the status/result has expired.",
    example: "Request examples",
    resultExample: "Illustrative result example",
    pagesIntro:
      "PDFs with two or more pages are split and converted in parallel; the final Markdown joins them in order. Use the main job ID and page numbers starting at 1. A single-page PDF is converted as a whole and has no page jobs.",
    pagesHead: ["Endpoint", "Usage"],
    pagesRows: [
      [
        "GET /jobs/{id}/pages",
        "Lists total_pages, pages_completed, pages_failed and pages[] with page_number, job_id, status, url, error_message and retry_count.",
      ],
      ["GET /jobs/{id}/pages/{n}/status", "Page status by number."],
      [
        "GET /jobs/{id}/pages/{n}/result",
        "JSON with result.markdown for a completed page; available before the merge.",
      ],
      [
        "GET /jobs/{id}/pages/{n}/pdf",
        "JSON with a signed PDF url, expires_in=900 and expires_at; does not return PDF bytes.",
      ],
      [
        "POST /jobs/{id}/pages/{n}/retry",
        "Retries a failed page, up to 3 manual attempts; save the new page_job_id returned.",
      ],
    ],
    pagesNote:
      "Before splitting, /pages may return 404; during creation, pages[] may be incomplete and job_id may be null. Poll again. Failed pages block the merge until recovered. Every endpoint requires authentication and checks ownership.",
    pdfNote:
      "Open the signed url directly, without Authorization or X-API-Key. It lasts 15 minutes; request another after it expires and preserve its entire query string. Do not add URL parameters.",
    engineNote:
      "The server may route pages through execution engines when configured. Use the same endpoints; an engine upload parameter does not select presets or queues.",
    imagesIntro:
      "Florence-2 describes images or extracts text with regions (OCR). All four inference routes create a job and wait for its result in the same request. The default request budget is 60 seconds; the task may continue up to its 120-second limit, both configurable on the server.",
    imagesHead: ["Endpoint", "Input / output"],
    imagesRows: [
      [
        "POST /images/describe/upload",
        "multipart: file, optional task, tags, project/project_id and folder/folder_id. Returns description and task.",
      ],
      [
        "POST /images/describe",
        "JSON: image_base64, optional filename, task, tags as an array and location. Same description response.",
      ],
      [
        "POST /images/ocr/upload",
        "multipart: file, tags and location. Returns text and lines[].",
      ],
      [
        "POST /images/ocr",
        "JSON: image_base64, optional filename, tags as an array and location. Same OCR; no task parameter.",
      ],
      [
        "GET /images/capabilities",
        "Worker state: dependencies_installed, model_downloaded, model_loaded, device_resolved and reason. Authenticated; does not start inference.",
      ],
    ],
    imageOptions:
      "PNG, JPEG, WEBP, BMP, GIF and TIFF, detected from their bytes. Default limits: 10 MB of decoded image data and 50 million pixels (VISION_MAX_IMAGE_SIZE_MB / VISION_MAX_IMAGE_PIXELS). Base64 accepts a data:image/...;base64, prefix and line breaks. Projects follow the same requirements as documents; repeated images create new jobs.",
    imageTasks:
      "task only accepts <CAPTION>, <DETAILED_CAPTION> and <MORE_DETAILED_CAPTION> (default, configurable via VISION_CAPTION_TASK). Arbitrary prompts are not accepted. In curl, use --form-string for these values: -F interprets < as reading a file.",
    imageResponse:
      "Success (200): job_id, status=completed, project, folder, image_base64 (echo of the original bytes), image_mime_type, image_bytes, image_sha256, width, height, model (model_id, revision, device, dtype) and duration_ms, plus the description or OCR. duration_ms is processing time reported by the worker, not total request time.",
    ocrNote:
      "Every line has text, quad_box=[x1,y1,x2,y2,x3,y3,x4,y4] and bbox=[x_min,y_min,x_max,y_max], in original image pixels. Images without text return 200 with empty text and lines=[]. The example below shows only OCR fields.",
    timeoutTitle: "Timeout and current limitations",
    timeout:
      "A 504 VISION_TIMEOUT includes detail.job_id, poll_url and result_url; the task continues. Poll poll_url for status and avoid automatically uploading again. Current limitation: /jobs/{id}/result requires Markdown, but the vision payload has no such field; recovery after completion may fail with 500. Save the successful response from the image request itself.",
    retention:
      "Vision results live in Redis for RESULT_TTL_SECONDS (1 hour by default), without Elasticsearch/MinIO persistence. The worker deletes the temporary image. Success status is not updated in MySQL; once the cache expires, the job list may revert to queued.",
    imageErrors:
      "Vision errors generally use detail={error_code,message,job_id}; authentication and validation errors may differ. 413: size; 422: invalid base64, format, task, pixels or location; 503: vision disabled, unavailable worker/model or no engine capacity (VISION_ENGINE_UNAVAILABLE, with Retry-After). /capabilities also returns 503 when vision is disabled.",
  },
};

function MediaSections({ lang, section }: { lang: Lang; section: string }) {
  const t = MEDIA_COPY[lang];
  const pt = lang === "pt";
  const block = (code: string) => (
    <CodeBlock code={code} copyLabel={COPY[lang].copy} />
  );
  const key = pt ? "SUA_CHAVE" : "YOUR_KEY";
  const project = pt ? "Documentos" : "Documents";
  const curl = (path: string, fields: string[], method = "POST") =>
    [
      `curl -X ${method} "${API_URL}${path}"`,
      `  -H "X-API-Key: ${key}"`,
      ...fields,
    ].join(" \\\n");

  return (
    <>
      {section === "documentos" && (
        <Section id="documentos" title={COPY[lang].sections.documents}>
          <Endpoint method="POST" path="/upload" />
          <Endpoint method="POST" path="/convert" />
          <P>{t.docsIntro}</P>
          <Table head={t.fields} rows={t.docsRows} />
          <Subheading>{t.presetsTitle}</Subheading>
          <Table head={t.presetsHead} rows={t.presets} />
          <P small>{t.formats}</P>
          <Subheading>{t.example}</Subheading>
          {block(
            curl("/upload", [
              `  -F "file=@${pt ? "relatorio" : "report"}.pdf"`,
              `  -F "project=${project}"`,
              `  -F "folder=${pt ? "Contratos" : "Contracts"}"`,
              '  -F "docling_preset=quality"',
              '  -F "tags=pdf,ocr"',
            ]),
          )}
          {block(
            curl("/convert", [
              '  -F "source_type=url"',
              '  -F "source=https://example.com/document.pdf"',
              `  -F "project=${project}"`,
            ]),
          )}
          <P small>{t.docsDuplicate}</P>
          <P>{t.docsResult}</P>
          {block(curl(`/jobs/${EXAMPLE_JOB_ID}/result`, [], "GET"))}
          <Subheading>{t.resultExample}</Subheading>
          {block(
            JSON.stringify(
              {
                job_id: EXAMPLE_JOB_ID,
                type: "main",
                status: "completed",
                result: {
                  markdown: "# Document\n\nContent...",
                  metadata: {
                    pages: 2,
                    words: 120,
                    format: "pdf",
                    size_bytes: 0,
                  },
                },
                completed_at: "2026-10-05T12:00:00",
              },
              null,
              2,
            ),
          )}
        </Section>
      )}

      {section === "paginas-pdf" && (
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
      )}

      {section === "imagens" && (
        <Section id="imagens" title={COPY[lang].sections.images}>
          <P>{t.imagesIntro}</P>
          <Table head={t.imagesHead} rows={t.imagesRows} />
          <P small>{t.imageOptions}</P>
          <P small>{t.imageTasks}</P>
          <Subheading>{t.example}</Subheading>
          {block(
            curl("/images/describe/upload", [
              '  -F "file=@photo.jpg"',
              `  -F "project=${project}"`,
              '  --form-string "task=<CAPTION>"',
            ]),
          )}
          {block(
            curl("/images/ocr/upload", [
              '  -F "file=@receipt.png"',
              `  -F "project=${project}"`,
              '  -F "tags=ocr"',
            ]),
          )}
          {block(
            `import base64\nimport requests\n\nwith open("receipt.png", "rb") as f:\n    image = base64.b64encode(f.read()).decode("ascii")\n\nr = requests.post(\n    "${API_URL}/images/ocr",\n    headers={"X-API-Key": "${key}"},\n    json={"image_base64": image, "filename": "receipt.png",\n          "project": "${project}", "tags": ["ocr"]},\n    timeout=75,\n)\nr.raise_for_status()\nprint(r.json()["text"])`,
          )}
          <P>{t.imageResponse}</P>
          <P small>{t.ocrNote}</P>
          {block(
            JSON.stringify(
              {
                text: "TOTAL 42.00",
                lines: [
                  {
                    text: "TOTAL 42.00",
                    quad_box: [12, 20, 180, 20, 180, 40, 12, 40],
                    bbox: [12, 20, 180, 40],
                  },
                ],
              },
              null,
              2,
            ),
          )}
          <Subheading>{t.timeoutTitle}</Subheading>
          <P>{t.timeout}</P>
          {block(
            JSON.stringify(
              {
                detail: {
                  error_code: "VISION_TIMEOUT",
                  message: "O job continua processando.",
                  job_id: EXAMPLE_JOB_ID,
                  poll_url: `/jobs/${EXAMPLE_JOB_ID}`,
                  result_url: `/jobs/${EXAMPLE_JOB_ID}/result`,
                },
              },
              null,
              2,
            ),
          )}
          <P small>{t.retention}</P>
          <P small>{t.imageErrors}</P>
          {block(curl("/images/capabilities", [], "GET"))}
        </Section>
      )}
    </>
  );
}

const LIVE_CAPTURE_COPY = {
  pt: {
    title: "Microfone ao vivo",
    intro:
      "Transmita áudio pelo microfone e receba legendas enquanto fala. A página /live permite escolher projeto e pasta, iniciar a captura, finalizar para salvar ou cancelar a sessão. Requer HTTPS ou localhost e permissão para usar o microfone.",
    availability:
      "Piloto opt-in, desabilitado por padrão. Depende da ativação pelo operador e de capacidade GPU disponível. A validação de qualidade e os critérios para produção ainda estão pendentes; os tempos medidos no piloto não são uma garantia de latência.",
    open: "Abrir captura de microfone",
    api: "Integração pela API",
    auth: "Crie a sessão com JWT ou API key e informe o projeto, como nos uploads. O retorno contém job_id, ws_url e um ticket de uso único válido por 60 segundos. Conecte à ws_url retornada e envie o ticket no primeiro frame JSON, sem colocá-lo na URL.",
    capture:
      "Espere session.ready antes de enviar áudio. O formato é PCM s16le, mono, 16 kHz. Cada bloco de 200 ms contém 3.200 amostras (6.400 bytes), precedidas por um cabeçalho little-endian de 12 bytes: seq uint32 e offset_samples uint64, ambos iniciando em zero. Avance seq por bloco e offset_samples pelas amostras enviadas. A cauda pode ser menor; o máximo por bloco é 500 ms.",
    events: "Eventos e encerramento",
    head: ["Evento / ação", "Comportamento"],
    rows: [
      [
        "transcript.partial",
        "Substitua o texto provisório pela revisão mais recente; não concatene revisões.",
      ],
      [
        "transcript.final",
        "Acrescente o segmento confirmado uma vez, em ordem de segment_id. Ele não será alterado.",
      ],
      [
        "finish",
        "Envie a cauda do áudio e depois finish com last_seq. Continue lendo até session.completed.",
      ],
      [
        "session.completed",
        "O resultado foi salvo. Use /jobs/{job_id}/result?format=txt|json|vtt|srt ou abra a página do job.",
      ],
      [
        "cancel / DELETE",
        "Encerra a sessão e descarta os parciais. Uma queda de conexão exige uma nova sessão.",
      ],
    ],
    limits:
      "Limites padrão: uma sessão simultânea por worker, até 30 minutos por sessão e 2 segundos de backlog. Falta de capacidade retorna 503 com Retry-After; não há fila de arquivos nem retry automático do áudio. LIVE_DISABLED indica piloto desligado; LIVE_NOT_READY, serviço ainda indisponível; LIVE_CAPACITY_FULL, capacidade ocupada.",
    privacy:
      "O áudio original não é armazenado. Ao finalizar, o texto e os formatos de legenda ficam no projeto, com acesso restrito ao dono. Finalizar espera a persistência; fechar a conexão não salva um resultado concluído.",
  },
  en: {
    title: "Live microphone",
    intro:
      "Stream microphone audio and receive captions as you speak. The /live page lets you choose a project and folder, start capture, finish to save or cancel the session. HTTPS or localhost and microphone permission are required.",
    availability:
      "Opt-in pilot, disabled by default. An operator must enable it and GPU capacity must be available. Quality validation and production criteria are still pending; pilot timings are not a latency guarantee.",
    open: "Open microphone capture",
    api: "API integration",
    auth: "Create a session with a JWT or API key and specify its project, as for uploads. The response includes job_id, ws_url and a single-use ticket valid for 60 seconds. Connect to the returned ws_url and send the ticket in the first JSON frame, without putting it in the URL.",
    capture:
      "Wait for session.ready before sending audio. Use mono 16 kHz PCM s16le. Each 200 ms block contains 3,200 samples (6,400 bytes), preceded by a 12-byte little-endian header: seq uint32 and offset_samples uint64, both starting at zero. Increment seq per block and offset_samples by the samples sent. The tail may be shorter; the maximum block is 500 ms.",
    events: "Events and completion",
    head: ["Event / action", "Behavior"],
    rows: [
      [
        "transcript.partial",
        "Replace provisional text with the latest revision; do not concatenate revisions.",
      ],
      [
        "transcript.final",
        "Append each confirmed segment once, in segment_id order. It will not change.",
      ],
      [
        "finish",
        "Send the audio tail, then finish with last_seq. Keep reading until session.completed.",
      ],
      [
        "session.completed",
        "The result has been saved. Use /jobs/{job_id}/result?format=txt|json|vtt|srt or open the job page.",
      ],
      [
        "cancel / DELETE",
        "Ends the session and discards partial captions. A disconnected session requires a new session.",
      ],
    ],
    limits:
      "Default limits: one concurrent session per worker, up to 30 minutes per session and 2 seconds of backlog. Unavailable capacity returns 503 with Retry-After; there is no file queue or automatic audio retry. LIVE_DISABLED means the pilot is off; LIVE_NOT_READY means the service is unavailable; LIVE_CAPACITY_FULL means capacity is occupied.",
    privacy:
      "The original audio is not stored. Finishing saves the text and caption formats in the project, accessible only to its owner. Finish waits for persistence; closing the connection does not save a completed result.",
  },
};

function LiveCaptureDocs({
  lang,
  copyLabel,
}: {
  lang: Lang;
  copyLabel: string;
}) {
  const t = LIVE_CAPTURE_COPY[lang];
  const key = lang === "pt" ? "SUA_API_KEY" : "YOUR_API_KEY";
  const body = JSON.stringify({
    project: lang === "pt" ? "Aulas" : "Classes",
    name: lang === "pt" ? "Transcrição ao vivo" : "Live transcript",
    language: "pt",
  });
  const create = `curl --fail -X POST "${API_URL}/transcribe/live/sessions" \\
  -H "X-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  --data '${body}'`;
  return (
    <Section id="microfone-live" title={t.title}>
      <P>{t.intro}</P>
      <P>
        <A href="/live">{t.open}</A>
      </P>
      <P small>{t.availability}</P>
      <P>
        {lang === "pt"
          ? "Idioma do piloto: Português."
          : "Pilot language: Portuguese."}
      </P>
      <Subheading>{t.api}</Subheading>
      <Endpoint method="POST" path="/transcribe/live/sessions" />
      <Endpoint method="GET" path="/transcribe/live/sessions/{job_id}" />
      <Endpoint method="DELETE" path="/transcribe/live/sessions/{job_id}" />
      <P>{t.auth}</P>
      <CodeBlock code={create} copyLabel={copyLabel} />
      <Endpoint method="WS" path="/transcribe/live/sessions/{job_id}/stream" />
      <CodeBlock
        code={'{"type":"authenticate","protocol":1,"ticket":"<ticket>"}'}
        copyLabel={copyLabel}
      />
      <P>{t.capture}</P>
      <Subheading>{t.events}</Subheading>
      <Table head={t.head} rows={t.rows} />
      <CodeBlock
        code={'{"type":"finish","last_seq":149}\n{"type":"cancel"}'}
        copyLabel={copyLabel}
      />
      <P small>
        {lang === "pt"
          ? "As mensagens acima são alternativas. last_seq deve ser a última sequência enviada na sua sessão."
          : "The messages above are alternatives. last_seq must be the last sequence sent in your session."}
      </P>
      <P>{t.limits}</P>
      <P>{t.privacy}</P>
    </Section>
  );
}

const COMPUTE_COPY = {
  pt: {
    title: "Compute: execução e capacidade",
    intro:
      "Compute reúne os motores que executam os jobs, sua capacidade e as rotas por funcionalidade. A instalação padrão usa os workers locais; contas Modal são opcionais e atendem transcrição de arquivos.",
    admin:
      "As telas permitem configurar e operar motores. Com o acesso delegado habilitado, cada usuário vê somente engines, perfis e ações autorizados. GPU, routing e status globais continuam restritos ao administrador. Os comandos Docker permanecem disponíveis.",
    head: ["Tela", "O que mostra"],
    profiles:
      "Biblioteca: modelo, host/provider, GPU, réplicas, concorrência, memória e warmup em revisões publicadas.",
    access:
      "Papéis, políticas, grants, escopos e delegação. O admin qualifica ambientes e consumidores físicos.",
    profileFlow:
      "Crie um perfil e publique uma revisão. Na engine, abra Configuração e escolha essa revisão em Perfil de execução. Vincular muda apenas o desejado; revise e confirme Aplicar perfil para executar. Desejado, aplicado e observado permanecem separados. A biblioteca e o acesso são opt-in e exigem migração.",
    engines:
      "Motores local/Modal, saúde, status, capacidade, teste, deploy e orçamento.",
    gpus: "GPUs declaradas e detectadas, VRAM orçada e uso atual. Valor desconhecido não significa zero.",
    routing:
      "Prioridade dos motores e backlog por funcionalidade. Sem rota, o job usa a fila local habitual.",
    status:
      "Despachante, worker remoto, tentativas em voo e workers configurados × vivos.",
    capacity:
      "Capacidade = workers × execuções por worker. A declaração não cria réplicas nem escolhe a placa CUDA do container. GPU local e Modal aceitam uma execução por worker; aumentar réplicas exige memória suficiente para todos os modelos na mesma placa.",
    health:
      "Um worker vivo pode estar ocupado ou com modelo ainda frio. A tela compara workers configurados e vivos; a confirmação de dispositivo e aquecimento vem dos logs e resultados. /health verifica a aplicação, enquanto o status Compute detalha a execução.",
    privacy:
      "Provider e motor são configurações distintas: faster-whisper/openai-whisper processam no worker; openai-api envia o áudio à OpenAI. O rótulo local informa qual executor atendeu. O orçamento Compute cobre contas Modal; cobranças de openai-api ficam fora dele. PDF e imagem têm rotas somente locais no adapter atual.",
    security:
      "Engines, perfis e controle exigem sessão JWT; o servidor valida papéis e escopos também antes dos efeitos. Credenciais Modal são somente escrita e exigem senha atual, com acesso explícito de bootstrap ou connection_manager. API keys não dão acesso ao controlador.",
    guide: "Setup, chaves, limites, deploy e benchmark no guia do operador",
    samples: "Leituras de diagnóstico (substitua o token JWT de admin)",
    fileCaptions:
      "Legendas parciais de arquivos acompanham um upload já enviado. A captura contínua de microfone foi implementada como piloto opt-in, com worker GPU próprio e ativação separada. Ela permanece desabilitada por padrão, com critérios de produção pendentes.",
  },
  en: {
    title: "Compute: execution and capacity",
    intro:
      "Compute brings together job execution engines, their capacity and per-feature routes. The default installation uses local workers; optional Modal accounts handle file transcription.",
    admin:
      "These screens let you configure and operate engines. When delegated access is enabled, users see only authorized engines, profiles and actions. Global GPU, routing and status remain administrator-only. Docker commands remain available.",
    head: ["Screen", "What it shows"],
    profiles:
      "Library: model, host/provider, GPU, replicas, concurrency, memory and warmup in published revisions.",
    access:
      "Roles, policies, grants, scopes and delegation. The administrator qualifies environments and physical consumers.",
    profileFlow:
      "Create a profile and publish a revision. Open the engine Configuration tab and select that revision under Execution profile. Binding changes desired state only; review and confirm Apply profile to execute. Desired, applied and observed states stay separate. The library and access are opt-in and require migration.",
    engines:
      "Local/Modal engines, health, status, capacity, tests, deployment and budget.",
    gpus: "Declared and detected GPUs, budgeted VRAM and current usage. An unknown value does not mean zero.",
    routing:
      "Engine priority and backlog per feature. Without a route, a job uses the usual local queue.",
    status:
      "Dispatcher, remote worker, in-flight attempts and configured versus live workers.",
    capacity:
      "Capacity = workers × executions per worker. Declaring capacity does not create replicas or select the container's CUDA device. Local GPU and Modal bindings accept one execution per worker; adding replicas requires enough memory for all models sharing the card.",
    health:
      "A live worker may be busy or have a cold model. The screen compares configured and live workers; logs and results confirm the device and model warmup. /health checks the application, while Compute status details execution.",
    privacy:
      "Providers and engines are separate settings: faster-whisper/openai-whisper process on the worker; openai-api sends audio to OpenAI. The local label identifies the executor. Compute budgets cover Modal accounts; openai-api charges are outside those budgets. The current adapter supports only local routes for PDFs and images.",
    security:
      "Engine, profile and control APIs require a JWT session; roles and scopes are checked again before effects. Modal credentials are write-only and require the current password plus bootstrap or connection_manager permission. API keys do not grant controller access.",
    guide:
      "Setup, keys, limits, deployment and benchmarks in the operator guide",
    samples: "Diagnostic reads (replace the admin JWT token)",
    fileCaptions:
      "File captions follow an upload that has already been sent. Continuous microphone capture is implemented as an opt-in pilot with a separate GPU worker and activation. It remains disabled by default, with production criteria pending.",
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
          [
            <A key="profiles" href="/admin/execution-profiles">
              /admin/execution-profiles
            </A>,
            t.profiles,
          ],
          [
            <A key="access" href="/admin/access">
              /admin/access
            </A>,
            t.access,
          ],
          [
            <A key="engines" href="/admin/engines">
              /admin/engines
            </A>,
            t.engines,
          ],
          [
            <A key="gpus" href="/admin/gpus">
              /admin/gpus
            </A>,
            t.gpus,
          ],
          [
            <A key="routing" href="/admin/routing">
              /admin/routing
            </A>,
            t.routing,
          ],
          [
            <A key="status" href="/admin/status">
              /admin/status
            </A>,
            t.status,
          ],
        ]}
      />
      <Subheading>
        {lang === "pt"
          ? "Perfis de execução e acesso"
          : "Execution profiles and access"}
      </Subheading>
      <P>{t.profileFlow}</P>
      <P>
        {lang === "pt"
          ? "Uma publicação fixa um payload imutável e os metadados do modelo aprovado. Novos rascunhos e publicações não mudam engines já vinculadas. Arquivar impede novos vínculos e preserva o histórico. O admin pode importar a configuração desejada legada como rascunho. Credenciais ficam na conexão e não entram no perfil."
          : "A publication pins an immutable payload and approved model metadata. New drafts and publications do not update engines already bound to a revision. Archiving prevents new bindings and preserves history. The administrator can import legacy desired settings as a draft. Credentials belong to the connection and are excluded from profiles."}
      </P>
      <Table
        head={
          lang === "pt"
            ? ["Papel", "Acesso concedível"]
            : ["Role", "Grantable access"]
        }
        rows={[
          [
            "observer",
            lang === "pt"
              ? "Ler perfis, engines e operações no escopo."
              : "Read profiles, engines and operations within scope.",
          ],
          [
            "profile_editor",
            lang === "pt"
              ? "Criar, revisar, publicar e arquivar perfis permitidos."
              : "Create, revise, publish and archive permitted profiles.",
          ],
          [
            "runtime_configurator",
            lang === "pt"
              ? "Vincular revisão publicada ao desejado da engine."
              : "Bind a published revision to engine desired state.",
          ],
          [
            "engine_operator",
            lang === "pt"
              ? "Preparar planos e executar somente as ações concedidas; cancelamento e recovery têm permissões próprias."
              : "Prepare plans and execute granted actions only; cancellation and recovery have separate permissions.",
          ],
          [
            "connection_manager",
            lang === "pt"
              ? "Gerenciar credenciais da conexão com senha atual; sem orçamento ou configuração bruta."
              : "Manage connection credentials with the current password; excludes budget and raw configuration.",
          ],
          [
            "access_admin",
            lang === "pt"
              ? "Delegar dentro de um envelope explícito de permissões, escopos, limites e validade; não recebe execução por esse papel."
              : "Delegate within an explicit envelope of permissions, scopes, limits and expiry; this role grants no execution rights.",
          ],
        ]}
      />
      <P>
        {lang === "pt"
          ? "Em Compute → Acesso, o admin classifica o ambiente das engines e qualifica todos os consumidores de cada recurso compartilhado. A política delimita engines/perfis, provider, feature, ambiente, modelo, host/GPU e tetos de réplicas, concorrência, CPU, memória, aquecimento e custo. Um grant completo precisa cobrir a decisão; não se somam partes de grants diferentes. O escopo cobre recursos do desejado e do último aplicado. Consumidor desconhecido ou fora do escopo bloqueia operação delegada."
          : "Under Compute → Access, the administrator classifies engine environments and qualifies every consumer of shared resources. Policies constrain engines/profiles, provider, feature, environment, model, host/GPU and limits for replicas, concurrency, CPU, memory, warmup and cost. One complete grant must cover the decision; parts of different grants cannot be combined. Scope covers desired and last applied resources. Unknown or out-of-scope consumers block delegated operation."}
      </P>
      <P>
        {lang === "pt"
          ? "O grant fixa uma revisão da política e uma validade UTC; uma nova revisão não amplia grants existentes. Revogação ou expiração parental invalida grants derivados. A autorização é verificada de novo antes de cada efeito. Revogar não desfaz uma chamada já admitida pelo provider; resultado desconhecido mantém exposição até observação ou cleanup autorizado."
          : "A grant pins a policy revision and UTC expiry; a new revision does not expand existing grants. Parent revocation or expiry invalidates derived grants. Authorization is checked again before each effect. Revocation cannot undo a call already admitted by the provider; unknown outcomes retain exposure until authorized observation or cleanup."}
      </P>
      <P>
        {lang === "pt"
          ? "Aquecimento usa uma duração de até 24 horas, resolvida uma vez no vínculo. Retry não renova o prazo. Em VERSION_CONFLICT, consulte o estado atual e revise a intenção antes de repetir. PUBLISHED_REVISION_REQUIRED pede revisão publicada; ENGINE_ENVIRONMENT_REQUIRED pede classificação da engine; MODEL_METADATA_CHANGED pede nova revisão compatível; 404 pode indicar recurso fora do escopo. RUNTIME_PROFILE_REQUIRED pede um vínculo, e HOST_AGENT_NOT_READY pede um heartbeat válido do host."
          : "Warmup uses a duration of up to 24 hours, resolved once on binding. Retry does not renew it. For VERSION_CONFLICT, read current state and review intent before retrying. PUBLISHED_REVISION_REQUIRED needs a published revision; ENGINE_ENVIRONMENT_REQUIRED needs engine classification; MODEL_METADATA_CHANGED needs a compatible new revision; 404 can mean an out-of-scope resource. RUNTIME_PROFILE_REQUIRED needs a binding, while HOST_AGENT_NOT_READY needs a valid host heartbeat."}
      </P>
      <Endpoint method="POST" path="/admin/execution-profiles/{id}/publish" />
      <Endpoint method="POST" path="/admin/access/grants" />
      <Endpoint method="POST" path="/admin/access/grants/{id}/revoke" />

      <Endpoint method="GET" path="/admin/execution-profiles" />
      <Endpoint
        method="POST"
        path="/admin/engines/{id}/runtime-profile/bind"
      />
      <P>{t.capacity}</P>
      <P>{t.health}</P>
      <P>{t.privacy}</P>
      <P>{t.security}</P>
      <Subheading>{t.samples}</Subheading>
      <Endpoint method="GET" path="/admin/engines/status" />
      <Endpoint method="GET" path="/admin/gpus" />
      <CodeBlock code={diagnostic} copyLabel={copyLabel} />
      <P small>{t.fileCaptions}</P>
      <P>
        <A href="https://github.com/geda-valentim/ingestify-to-ai/blob/main/docs/features/engines.md">
          {t.guide}
        </A>
      </P>
    </Section>
  );
}

function PlatformSettingsDocs({ lang }: { lang: Lang }) {
  const pt = lang === "pt";
  return (
    <Section
      id="platform-settings"
      title={pt ? "Configurações da plataforma" : "Platform settings"}
    >
      <P>
        {pt ? (
          <>
            Em <A href="/admin/settings">Admin → Settings → Allow signups</A>,
            um administrador pode liberar ou fechar novos cadastros. A alteração
            é salva imediatamente e permanece após reiniciar a plataforma.
          </>
        ) : (
          <>
            Under <A href="/admin/settings">Admin → Settings → Allow signups</A>
            , an administrator can enable or disable new registrations. Changes
            are saved immediately and persist across restarts.
          </>
        )}
      </P>
      <Subheading>
        {pt ? "Controle de cadastro" : "Registration control"}
      </Subheading>
      <Endpoint method="GET" path="/auth/registration-settings" />
      <P>
        {pt
          ? "Consulta pública da disponibilidade de cadastro, sem autenticação e sem cache HTTP. Apenas essa política é exposta."
          : "Public registration availability, without authentication or HTTP caching. Only this policy is exposed."}
      </P>
      <CodeBlock
        code={'{"signup_enabled": true}'}
        copyLabel={COPY[lang].copy}
      />
      <Endpoint method="GET" path="/admin/settings" />
      <Endpoint method="PATCH" path="/admin/settings" />
      <P>
        {pt
          ? "A leitura e a alteração das configurações exigem uma sessão de administrador. Envie false para fechar ou true para reabrir; somente booleanos JSON são aceitos, e campos desconhecidos são recusados."
          : "Reading and updating settings requires an administrator session. Send false to close registration or true to reopen it; only JSON booleans are accepted, and unknown fields are rejected."}
      </P>
      <CodeBlock
        code={`curl -X PATCH "${API_URL}/admin/settings" \\
  -H "Authorization: Bearer <admin-token>" \\
  -H "Content-Type: application/json" \\
  --data '{"signup_enabled": false}'`}
        copyLabel={COPY[lang].copy}
      />
      <Subheading>
        {pt ? "Quando o cadastro está fechado" : "When registration is closed"}
      </Subheading>
      <P>
        {pt ? (
          <>
            O endpoint <C>POST /auth/register</C> retorna <C>403</C>, inclusive
            em chamadas diretas ou feitas por um administrador. O login oculta o
            link de cadastro, e a página de registro informa que o cadastro está
            fechado. Login, sessões e contas existentes continuam funcionando.
          </>
        ) : (
          <>
            The <C>POST /auth/register</C> endpoint returns <C>403</C>,
            including direct calls or calls by administrators. Login hides the
            registration link, and the registration page shows that registration
            is closed. Login, sessions and existing accounts keep working.
          </>
        )}
      </P>
      <P small>
        {pt
          ? "O padrão de uma instalação sem configuração é cadastro habilitado. As páginas atualizam a política ao abrir, ao recuperar foco e a cada 30 segundos; a API verifica a configuração atual em cada tentativa de cadastro. Se a consulta falhar, o formulário não é liberado."
          : "An installation without a saved policy defaults to registration enabled. Pages refresh the policy on load, on focus and every 30 seconds; the API checks the current setting on every registration attempt. If the policy request fails, the form is not enabled."}
      </P>
    </Section>
  );
}

export function TopicContent({ topic, lang }: { topic: string; lang: Lang }) {
  const t = COPY[lang];
  const code = samples(lang);
  const block = (c: string) => <CodeBlock code={c} copyLabel={t.copy} />;
  switch (topic) {
    case "datalakes":
      return (
        <Section
          id="datalakes"
          title={
            lang === "pt" ? "Datalakes e buckets" : "Datalakes and buckets"
          }
        >
          <P>
            {lang === "pt"
              ? "Em Datalakes, cadastre uma conexão AWS S3, MinIO, Google Cloud Storage ou Azure Blob Storage. Configure credenciais, buckets permitidos e bucket/pasta padrão. Cada conexão pertence ao seu usuário; as credenciais são criptografadas e não voltam nas respostas da API."
              : "In Datalakes, add an AWS S3, MinIO, Google Cloud Storage or Azure Blob Storage connection. Set credentials, allowed buckets and a default bucket/folder. Connections belong to your user; credentials are encrypted and never returned by the API."}
          </P>
          <P>
            {lang === "pt"
              ? "Ao enviar um documento, áudio/vídeo ou iniciar uma captura ao vivo, escolha a conexão, o bucket e a pasta em Destino dos resultados. Na aba Datalake do dashboard você também pode selecionar um arquivo que já esteja no bucket. No Azure, o bucket corresponde ao container."
              : "When uploading a document, audio/video or starting live capture, choose a connection, bucket and folder under Result destination. The dashboard Datalake tab also lets you process a file already in a bucket. For Azure, the bucket is the container."}
          </P>
          <A href="/datalakes">
            {lang === "pt" ? "Configurar conexões" : "Configure connections"}
          </A>
          <Subheading>
            {lang === "pt" ? "Solicitação pela API" : "API request"}
          </Subheading>
          {block(
            `curl -X POST '${API_URL}/transcribe' \\\n  -H 'Authorization: Bearer YOUR_TOKEN' \\\n  -F 'file=@meeting.mp3' \\\n  -F 'project=Meetings' \\\n  -F 'datalake_connection_id=YOUR_CONNECTION_ID' \\\n  -F 'datalake_bucket=transcripts' \\\n  -F 'datalake_prefix=meetings/2026'`,
          )}
          <P>
            {lang === "pt"
              ? "Os mesmos campos são aceitos em /upload e /convert. Para captura ao vivo, envie datalake: {connection_id, bucket, prefix} no JSON de criação da sessão."
              : "The same fields are accepted by /upload and /convert. For live capture, send datalake: {connection_id, bucket, prefix} in the session creation JSON."}
          </P>
          <Endpoint method="GET" path="/jobs/{job_id}/datalake" />
          <Endpoint method="POST" path="/jobs/{job_id}/datalake/retry" />
          <P>
            {lang === "pt"
              ? "A entrega tem status próprio. Se falhar, corrija a conexão e use Tentar entrega novamente na página do job, sem repetir a conversão ou transcrição. Os arquivos ficam em pasta/job_id/: result.json, result.md, metadata.json e, para transcrições, TXT, SRT, VTT e JSON. Excluir o job ou a conexão no Ingestify preserva os arquivos do bucket externo."
              : "Delivery has its own status. If it fails, fix the connection and retry delivery from the job page without repeating conversion or transcription. Files are stored under folder/job_id/: result.json, result.md, metadata.json and, for transcripts, TXT, SRT, VTT and JSON. Deleting an Ingestify job or connection preserves files in the external bucket."}
          </P>
        </Section>
      );
    case "introduction":
      return (
        <Section id="introducao" title={t.sections.intro}>
          {t.intro}
          <Table rows={t.introRows} />
        </Section>
      );
    case "authentication":
      return (
        <Section id="autenticacao" title={t.sections.auth}>
          {t.authIntro}
          <Table head={t.authHead} rows={t.authRows} />
          {t.authNote}
        </Section>
      );
    case "projects":
      return (
        <Section id="projetos" title={t.sections.projects}>
          {t.projectsIntro}
          <Table head={t.projectsHead} rows={t.projectsRows} />
          {t.projectsResolution}
          {t.projectsManagement}
          <Subheading>{t.projectsRequiredTitle}</Subheading>
          {block(RESPONSES.projectRequired)}
          {t.projectsNormalization}
          {t.projectsPrecedence}
          <Subheading>{t.projectsExampleTitle}</Subheading>
          {block(code.curlProject)}
        </Section>
      );
    case "transcription":
      return (
        <Section id="transcribe" title={t.sections.transcribe}>
          <Endpoint method="POST" path="/transcribe" />
          {t.transcribeIntro}

          <Subheading>{t.paramsTitle}</Subheading>
          <Table head={t.paramsHead} rows={t.paramsRows} />

          <Subheading>{t.filesTitle}</Subheading>
          <Table head={t.filesHead} rows={t.filesRows} />
          {t.filesNote}

          <Subheading>{t.exampleTitle}</Subheading>
          <div className="space-y-3">
            <details open className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">curl</summary>
              <div className="pt-3">{block(code.curlCreate)}</div>
            </details>
            <details className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">Python</summary>
              <div className="pt-3">{block(code.python)}</div>
            </details>
            <details className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">
                JavaScript
              </summary>
              <div className="pt-3">{block(code.javascript)}</div>
            </details>
          </div>

          <Subheading>{t.responseTitle}</Subheading>
          {block(RESPONSES.create)}
          <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
            {t.duplicate}
          </div>
        </Section>
      );
    case "job-status":
      return (
        <Section id="transcribe-status" title={t.sections.status}>
          <Endpoint method="GET" path="/jobs/{job_id}" />
          {t.statusIntro}
          {block(code.curlStatus)}
          {block(RESPONSES.status)}
          {t.statusFields}
          {t.statusNote}
        </Section>
      );
    case "file-captions":
      return (
        <Section id="transcribe-live" title={t.sections.live}>
          <Endpoint
            method="GET"
            path="/jobs/{job_id}/transcript/partial?since=N"
          />
          {t.liveIntro}
          {block(code.curlLive)}
          {block(RESPONSES.live)}
        </Section>
      );
    case "results":
      return (
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

          <div className="space-y-3">
            <details open className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">markdown</summary>
              <div className="pt-3">
                {block(RESPONSES.markdown)}
                <p className="pt-2 text-sm text-muted-foreground">
                  {t.deviceNote}
                </p>
              </div>
            </details>
            <details className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">vtt</summary>
              <div className="pt-3">{block(RESPONSES.vtt)}</div>
            </details>
            <details className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">srt</summary>
              <div className="pt-3">{block(RESPONSES.srt)}</div>
            </details>
            <details className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">txt</summary>
              <div className="pt-3">{block(RESPONSES.txt)}</div>
            </details>
            <details className="rounded-lg border p-4">
              <summary className="cursor-pointer font-medium">json</summary>
              <div className="pt-3">
                {block(RESPONSES.json)}
                <p className="pt-2 text-sm text-muted-foreground">
                  {t.wordsNote}
                </p>
              </div>
            </details>
          </div>
        </Section>
      );
    case "errors":
      return (
        <Section id="transcribe-erros" title={t.sections.errors}>
          {t.errorsIntro}
          <Table
            head={t.errorsHead}
            rows={Object.entries(t.errors).map(([status, when]) => [
              <C key="s">{status}</C>,
              when,
            ])}
          />
        </Section>
      );
    case "documents":
      return <MediaSections lang={lang} section="documentos" />;
    case "pdf-pages":
      return <MediaSections lang={lang} section="paginas-pdf" />;
    case "images":
      return <MediaSections lang={lang} section="imagens" />;
    case "live":
      return <LiveCaptureDocs lang={lang} copyLabel={t.copy} />;
    case "platform-settings":
      return <PlatformSettingsDocs lang={lang} />;
    case "compute":
      return <ComputeDocs lang={lang} copyLabel={t.copy} />;
    default:
      return null;
  }
}
