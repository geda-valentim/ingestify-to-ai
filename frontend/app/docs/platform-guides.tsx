import Link from "next/link";
import { DOCS_TOPICS, docsHref, type DocsLang } from "./topics";

type Text = { pt: string; en: string };
type Guide = {
  goal: Text;
  requirements: Text[];
  parts: { title: Text; paragraphs?: Text[]; steps?: Text[] }[];
  outcome: Text;
  problems: Text[];
  actions: { href: string; label: Text }[];
};
const t = (pt: string, en: string): Text => ({ pt, en });

/** Instructions checked against the routed UI, rather than unfinished upload prototypes. */
const guides: Record<string, Guide> = {
  "platform-start": {
    goal: t(
      "Transforme um arquivo em um resultado que você pode consultar e baixar. Comece com um PDF digital pequeno ou uma imagem para validar o fluxo antes de enviar um lote.",
      "Turn a file into a result you can inspect and download. Start with a small digital PDF or an image to validate the workflow before processing a batch.",
    ),
    requirements: [
      t(
        "Uma conta com sessão iniciada e um arquivo local. Os guias são públicos; as telas de processamento exigem login.",
        "A signed-in account and a local file. Guides are public; processing screens require login.",
      ),
      t(
        "Uma engine disponível para a operação. O envio aceita o pedido, mas o processamento depende dos workers e da capacidade configurados pela administração.",
        "An engine available for the operation. Submission accepts the request, but processing depends on the workers and capacity configured by the administrator.",
      ),
    ],
    parts: [
      {
        title: t("Enviar e acompanhar", "Submit and follow progress"),
        steps: [
          t(
            "Abra /convert (New conversion). Em Project, selecione um projeto existente ou informe um nome novo. O projeto é obrigatório; Folder é opcional. Nomes novos são criados quando a solicitação é enviada.",
            "Open /convert (New conversion). Under Project, choose an existing project or enter a new name. Project is required; Folder is optional. New names are created when the request is submitted.",
          ),
          t(
            "Na aba File, escolha o arquivo. Para documento, informe um Custom Name e Tags se forem úteis. Para imagem, escolha o modo e preencha suas opções específicas.",
            "In the File tab, choose the file. For a document, add a Custom Name and Tags when useful. For an image, choose the mode and fill its specific options.",
          ),
          t(
            "Clique em Convert to Markdown ou Processar imagem. Após a confirmação, a plataforma abre /jobs/{id}. Guarde essa URL para voltar ao mesmo resultado.",
            "Click Convert to Markdown or Processar imagem. After confirmation, the platform opens /jobs/{id}. Save this URL to return to the same result.",
          ),
          t(
            "Acompanhe o status. Um job na fila ainda não produziu o resultado final. Quando terminar, revise a visualização e baixe o formato desejado.",
            "Follow the status. A queued job has not produced its final result yet. When it finishes, review the viewer and download the desired format.",
          ),
          t(
            "Abra /jobs para encontrar o histórico. Selecione o projeto ou a pasta e abra o job para consultar o resultado novamente.",
            "Open /jobs to find the history. Choose the project or folder and open the job to read its result again.",
          ),
        ],
      },
      {
        title: t("Escolher o caminho disponível", "Choose an available path"),
        paragraphs: [
          t(
            "O envio local de documentos e imagens funciona em /convert. As abas URL, Google Drive e Dropbox dessa tela ainda mostram uma mensagem de recurso futuro; use os endpoints documentados quando precisar integrar fontes externas. Para áudio/vídeo gravado, envie pela API de transcrição e consulte o job pela plataforma. O microfone tem sua própria tela /live.",
            "Local document and image submission works in /convert. The URL, Google Drive and Dropbox tabs on that screen still show a future-feature message; use the documented endpoints for external-source integrations. Submit recorded audio/video through the transcription API and inspect its job in the platform. The microphone has its own /live screen.",
          ),
        ],
      },
    ],
    outcome: t(
      "Um job associado ao projeto, uma URL de acompanhamento e um resultado consultável. O tipo do arquivo determina quais visualizações e downloads estarão disponíveis.",
      "A project-associated job, a tracking URL and an inspectable result. The file type determines the available viewers and downloads.",
    ),
    problems: [
      t(
        "Botão desabilitado: escolha um projeto e um arquivo; em imagens, corrija consultas, regiões ou destino que estejam inválidos.",
        "Disabled button: choose a project and a file; for images, correct invalid queries, regions or destination options.",
      ),
      t(
        "Falha no envio: leia a mensagem do formulário. Verifique formato, tamanho e sessão antes de repetir. Uma falha de leitura do resultado deve ser investigada no job existente.",
        "Submission failed: read the form message. Check the format, size and session before retrying. Investigate a result-reading failure in the existing job.",
      ),
    ],
    actions: [
      {
        href: "/convert",
        label: t("Enviar meu primeiro arquivo", "Submit my first file"),
      },
      { href: "/jobs", label: t("Abrir meus jobs", "Open my jobs") },
    ],
  },
  "platform-projects-jobs": {
    goal: t(
      "Organize os pedidos em projetos e pastas e encontre resultados sem perder o contexto de cada cliente ou trabalho.",
      "Organize requests in projects and folders and find results without losing the context of each customer or assignment.",
    ),
    requirements: [
      t(
        "Uma conta e pelo menos um job para explorar o histórico. Você também pode criar um projeto ao enviar o primeiro arquivo.",
        "An account and at least one job to explore the history. You can also create a project while submitting your first file.",
      ),
    ],
    parts: [
      {
        title: t(
          "Projetos e pastas nas telas",
          "Projects and folders in the screens",
        ),
        steps: [
          t(
            "No formulário de envio, selecione Project; escolha uma pasta em Folder ou deixe o job na raiz do projeto. Para cadastrar um nome novo, use a opção de criação no seletor e envie a solicitação.",
            "In the submission form, select Project; choose a Folder or leave the job at the project root. To add a new name, use the creation option in the selector and submit the request.",
          ),
          t(
            "Abra /jobs. No desktop, a lateral lista projetos e pastas; no celular, use os seletores de projeto e pasta. No folder mostra os jobs sem pasta; All folders mantém todo o projeto.",
            "Open /jobs. On desktop, the sidebar lists projects and folders; on mobile, use the project and folder selectors. No folder shows jobs without a folder; All folders keeps the whole project.",
          ),
          t(
            "Combine a seleção com os filtros de status e tipo. Use a busca disponível para localizar o nome ou pesquisar conteúdo processado; busca de conteúdo não equivale a uma análise de todas as conversas.",
            "Combine the selection with status and type filters. Use the available search to find a name or search processed content; content search is not an analysis of all conversations.",
          ),
          t(
            "Abra o job. Confira nome, projeto, estado e configuração antes de ler o resultado. Uma conversão nova iniciada dentro de um projeto conserva esse contexto no formulário.",
            "Open the job. Check its name, project, state and configuration before reading the result. A new conversion started inside a project preserves that context in the form.",
          ),
        ],
      },
      {
        title: t("Interpretar o acompanhamento", "Interpret job progress"),
        paragraphs: [
          t(
            "pending/queued indicam que o pedido espera processamento; processing indica execução; completed libera o resultado final. A análise de imagem pode terminar partial quando somente parte das etapas foi concluída. failed ou cancelled exigem consultar a mensagem e os resultados disponíveis, em vez de presumir sucesso.",
            "pending/queued mean the request is waiting; processing means execution; completed makes the final result available. Image analysis may finish partial when only some steps completed. For failed or cancelled, inspect the message and available results rather than assuming success.",
          ),
          t(
            "Em PDFs divididos, acompanhe as páginas e abra uma página específica para diagnosticar falhas. Em transcrição, o andamento pode mostrar segundos transcritos e segmentos parciais. O percentual representa avanço do pipeline, não precisão do modelo.",
            "For split PDFs, track pages and open a specific page to diagnose failures. For transcription, progress may show transcribed seconds and partial segments. The percentage represents pipeline progress, not model accuracy.",
          ),
        ],
      },
    ],
    outcome: t(
      "Uma visão filtrada do histórico e acesso ao resultado certo por projeto e pasta. Esses agrupamentos organizam jobs; não criam automaticamente resumos ou análises entre vários jobs.",
      "A filtered history view and access to the correct result by project and folder. These groups organize jobs; they do not automatically create summaries or analyses across jobs.",
    ),
    problems: [
      t(
        "Histórico vazio: confira projeto, pasta e filtros ativos antes de concluir que o job desapareceu. Atualize a listagem se a solicitação acabou de ser enviada.",
        "Empty history: check the project, folder and active filters before concluding that a job disappeared. Refresh the list if the request was just submitted.",
      ),
      t(
        "Job na fila por muito tempo: confira a razão exibida. Capacidade, orçamento e engine indisponível precisam da administração; reenviar repetidamente só cria mais pedidos.",
        "Job queued for too long: check the displayed reason. Capacity, budget and an unavailable engine require an administrator; repeatedly resubmitting only creates more requests.",
      ),
    ],
    actions: [
      { href: "/jobs", label: t("Organizar meus jobs", "Organize my jobs") },
      {
        href: "/convert",
        label: t("Enviar para um projeto", "Submit to a project"),
      },
    ],
  },
  "platform-documents": {
    goal: t(
      "Converta um documento em Markdown e confira o texto extraído, principalmente tabelas e páginas escaneadas.",
      "Convert a document to Markdown and review extracted text, especially tables and scanned pages.",
    ),
    requirements: [
      t(
        "Um documento compatível com a instalação e uma engine de conversão disponível. Um PDF digital pequeno é uma boa primeira validação.",
        "A document supported by the installation and an available conversion engine. A small digital PDF is a good first validation.",
      ),
    ],
    parts: [
      {
        title: t("Converter e revisar", "Convert and review"),
        steps: [
          t(
            "Abra /convert, selecione projeto/pasta e adicione o documento na aba File. Use Custom Name e Tags para facilitar a localização no histórico.",
            "Open /convert, select a project/folder and add the document in the File tab. Use Custom Name and Tags to make it easier to locate in the history.",
          ),
          t(
            "Clique em Convert to Markdown e abra o job criado. Aguarde a conclusão; para PDF dividido, acompanhe o total de páginas concluídas e com falha.",
            "Click Convert to Markdown and open the created job. Wait for completion; for a split PDF, follow the completed and failed page counts.",
          ),
          t(
            "Compare a visualização do resultado com o documento original. Confira títulos, ordem de leitura, tabelas e números. Use as páginas individuais, quando disponíveis, para localizar uma extração problemática.",
            "Compare the result viewer with the original document. Check headings, reading order, tables and numbers. Use individual pages, when available, to locate a problematic extraction.",
          ),
          t(
            "Use as opções de cópia/download do resultado para levar o Markdown à aplicação de destino. Para automatizar o consumo de JSON e metadados, consulte a referência de resultados.",
            "Use the result copy/download options to take Markdown to the destination application. To automate JSON and metadata consumption, see the results reference.",
          ),
        ],
      },
      {
        title: t("Escolher uma fonte", "Choose a source"),
        paragraphs: [
          t(
            "O guia das telas usa upload local. As abas URL/Drive/Dropbox em /convert ainda não concluem o envio; os contratos de /convert descrevem a integração dessas fontes pela API. A entrega externa de documentos ainda não está ligada ao fluxo de conversão desta versão; o resultado fica disponível no job.",
            "This screen guide uses local upload. URL/Drive/Dropbox tabs in /convert do not yet complete submission; /convert contracts describe API integration for those sources. External document delivery is not yet connected to this version conversion flow; the result remains available in the job.",
          ),
        ],
      },
    ],
    outcome: t(
      "Markdown associado ao job e ao projeto. Em PDFs divididos, o job principal reúne o documento e os jobs de página permitem inspeção individual.",
      "Markdown associated with the job and project. For split PDFs, the main job assembles the document and page jobs allow individual inspection.",
    ),
    problems: [
      t(
        "Texto ausente em scan: OCR e configurações de tabelas pertencem ao motor/perfil da instalação. Peça à administração para verificar o perfil antes de processar o documento novamente.",
        "Missing scan text: OCR and table settings belong to the installation engine/profile. Ask the administrator to check the profile before processing the document again.",
      ),
      t(
        "Páginas com falha: registre job ID e números de página para o diagnóstico. Um resultado legível não prova que todas as páginas foram extraídas.",
        "Failed pages: record the job ID and page numbers for diagnosis. A readable result does not prove every page was extracted.",
      ),
    ],
    actions: [
      {
        href: "/convert",
        label: t("Converter um documento", "Convert a document"),
      },
      {
        href: "/jobs",
        label: t(
          "Revisar documentos processados",
          "Review processed documents",
        ),
      },
    ],
  },
  "platform-transcription": {
    goal: t(
      "Leia transcrições de arquivos e capture fala pelo microfone, distinguindo legendas temporárias do resultado salvo.",
      "Read file transcripts and capture microphone speech while distinguishing temporary captions from a saved result.",
    ),
    requirements: [
      t(
        "Para arquivos: um job enviado a /transcribe pela API. O formulário atual /convert é de documentos e imagens; não oferece um envio de transcrição de arquivo.",
        "For files: a job submitted to /transcribe through the API. The current /convert form handles documents and images; it does not offer file transcription submission.",
      ),
      t(
        "Para microfone: HTTPS ou localhost, permissão do navegador, projeto escolhido e capacidade live-transcription disponível. A tela /live informa o idioma Português.",
        "For microphone: HTTPS or localhost, browser permission, a selected project and available live-transcription capacity. The /live screen specifies Portuguese as the language.",
      ),
    ],
    parts: [
      {
        title: t("Ler um arquivo transcrito", "Read a transcribed file"),
        steps: [
          t(
            "Envie áudio/vídeo usando a referência de Transcrição de áudio e vídeo. Abra o job em /jobs e filtre por Transcriptions para encontrá-lo.",
            "Submit audio/video using the Audio and video transcription reference. Open its job in /jobs and filter by Transcriptions to find it.",
          ),
          t(
            "Durante o processamento, acompanhe segundos transcritos e segmentos quando disponíveis. Trechos parciais podem mudar; o resultado final aparece após a conclusão.",
            "During processing, track transcribed seconds and segments when available. Partial snippets may change; the final result appears after completion.",
          ),
          t(
            "No resultado, consulte segmentos com tempos, texto/Markdown e metadados. Baixe TXT, SRT, VTT ou JSON conforme a aplicação; os tempos permitem sincronizar as legendas.",
            "In the result, inspect timed segments, text/Markdown and metadata. Download TXT, SRT, VTT or JSON for your application; timestamps allow caption synchronization.",
          ),
        ],
      },
      {
        title: t("Capturar pelo microfone", "Capture microphone audio"),
        steps: [
          t(
            "Abra /live. Informe Nome, Project e Folder opcional. Identificar falantes durante a captura é uma opção; sua disponibilidade depende da configuração e capacidade da instalação.",
            "Open /live. Enter Nome, Project and an optional Folder. Identificar falantes durante a captura is optional; availability depends on the installation configuration and capacity.",
          ),
          t(
            "Clique em Iniciar microfone e permita o acesso. Aguarde a verificação de disponibilidade e o estado Ouvindo. Acompanhe as legendas enquanto fala.",
            "Click Iniciar microfone and allow microphone access. Wait for the availability check and Ouvindo state. Follow captions while speaking.",
          ),
          t(
            "Clique em Finalizar para encerrar e salvar. Aguarde Transcrição salva e abra Ver resultado e baixar legendas. Cancelar abandona a sessão; não equivale a finalizar e salvar.",
            "Click Finalizar to end and save. Wait for Transcrição salva and open Ver resultado e baixar legendas. Cancelar abandons the session; it is not equivalent to finishing and saving.",
          ),
        ],
      },
      {
        title: t(
          "Disponibilidade e privacidade da captura",
          "Capture availability and privacy",
        ),
        paragraphs: [
          t(
            "A tela informa que o áudio não é armazenado; a transcrição final é salva no projeto. O processamento depende da engine live e das opções habilitadas. A captura pode ser interrompida por perda de conexão ou ausência de capacidade; consulte a mensagem antes de iniciar outra sessão.",
            "The screen states that audio is not stored; the final transcript is saved in the project. Processing depends on the live engine and enabled options. Capture may be interrupted by connection loss or lack of capacity; read the message before starting another session.",
          ),
        ],
      },
    ],
    outcome: t(
      "Um transcript com segmentos temporais e formatos de exportação. Captura finalizada cria um resultado salvo; legendas vistas durante uma sessão cancelada não são garantia de um job final.",
      "A transcript with timed segments and export formats. Finished capture creates a saved result; captions seen during a cancelled session do not guarantee a final job.",
    ),
    problems: [
      t(
        "Microfone bloqueado: permita o acesso no navegador e confira se está em HTTPS/localhost. Verifique se outro aplicativo está usando o dispositivo.",
        "Microphone blocked: allow browser access and check HTTPS/localhost. Check whether another application is using the device.",
      ),
      t(
        "Falantes ou engine indisponíveis: desative a opção não disponível ou peça à administração para conferir live-transcription. A captura não deve ser tratada como ativa até aparecer Ouvindo.",
        "Speakers or engine unavailable: disable the unavailable option or ask the administrator to check live-transcription. Do not treat capture as active until Ouvindo appears.",
      ),
    ],
    actions: [
      { href: "/live", label: t("Abrir captura ao vivo", "Open live capture") },
      {
        href: "/jobs",
        label: t("Consultar transcrições", "Inspect transcripts"),
      },
    ],
  },
  "platform-images": {
    goal: t(
      "Use Full Analysis para explorar descrição, texto, objetos e regiões de uma imagem em um único job, sem confundir número de famílias com número de resultados.",
      "Use Full Analysis to explore an image description, text, objects and regions in one job, without confusing family count with result count.",
    ),
    requirements: [
      t(
        "Uma imagem compatível, um projeto e uma engine de visão disponível. O perfil Florence tem 15 famílias. O perfil que inclui rostos e expressões tem 18 e depende da feature facial estar habilitada e disponível.",
        "A supported image, a project and an available vision engine. The Florence profile has 15 families. The profile including faces and expressions has 18 and depends on the facial feature being enabled and available.",
      ),
    ],
    parts: [
      {
        title: t("Configurar o pedido", "Configure the request"),
        steps: [
          t(
            "Abra /convert, escolha projeto/pasta e selecione uma imagem na aba File. Na seção de opções da imagem, selecione Full Analysis.",
            "Open /convert, choose a project/folder and select an image in the File tab. In the image options section, select Full Analysis.",
          ),
          t(
            "Escolha o perfil disponível. Se quiser localizar objetos específicos, informe até três consultas, uma por linha. As consultas alimentam tarefas guiadas por texto; não são uma pergunta de chat sobre todo o histórico.",
            "Choose an available profile. To locate specific objects, enter up to three queries, one per line. Queries feed text-guided tasks; they are not a chat question about the full history.",
          ),
          t(
            "Para tarefas por região, use o seletor visual e confira as regiões escolhidas. Deixar consultas e regiões vazias usa a estratégia automática do perfil; o plano final depende dos objetos encontrados e dos limites.",
            "For region tasks, use the visual selector and review selected regions. Leaving queries and regions empty uses the profile automatic strategy; the final plan depends on detected objects and limits.",
          ),
          t(
            "Se quiser exportar para seu bucket, configure Destino dos resultados e confira a prévia de particionamento antes de clicar em Processar imagem.",
            "To export to your bucket, configure Destino dos resultados and review the partition preview before clicking Processar imagem.",
          ),
        ],
      },
      {
        title: t("Navegar pelo resultado", "Navigate the result"),
        steps: [
          t(
            "Leia o resumo e o status. Famílias concluídas conta tipos de tarefa; Resultados concluídos conta execuções dessas tarefas. Uma família pode ter várias instâncias, por consulta ou região.",
            "Read the summary and status. Famílias concluídas counts task types; Resultados concluídos counts task executions. A family may have several instances, by query or region.",
          ),
          t(
            "Selecione uma família na lateral; no celular, use o seletor Selecione uma família. Escolha a instância em Resultados da família quando houver várias.",
            "Select a family in the sidebar; on mobile, use the Selecione uma família selector. Choose an instance under Resultados da família when several are available.",
          ),
          t(
            "Confira o texto e a aba Regiões. A imagem mostra caixas ou polígonos da etapa selecionada; use os controles de camadas para mostrar/ocultar e clique nas regiões para relacionar rótulos e posição.",
            "Inspect the text and Regiões tab. The image displays boxes or polygons for the selected step; use layer controls to show/hide them and click regions to relate labels to their positions.",
          ),
          t(
            "Leia o motivo de etapas sem resultado ou com falha. partial significa cobertura incompleta, não ausência de todo o resultado. failed ou cancelled também podem conservar etapas concluídas; explore o que está disponível.",
            "Read the reason for steps with no result or a failure. partial means incomplete coverage, not an entirely absent result. failed or cancelled may also retain completed steps; explore what is available.",
          ),
          t(
            "Use Download JSON para o resultado estruturado e Download Markdown para o relatório legível. Guarde a URL do job; recarregar a página deve recuperar o resultado persistido.",
            "Use Download JSON for structured output and Download Markdown for the readable report. Save the job URL; refreshing the page should retrieve its persisted result.",
          ),
        ],
      },
      {
        title: t("Interpretar os modelos", "Interpret model output"),
        paragraphs: [
          t(
            "Full Analysis reúne as famílias implementadas no perfil escolhido, respeitando limites de etapas e tempo. Não significa todas as análises possíveis de qualquer modelo. Rótulos, OCR e expressões são inferências sujeitas a erro: confira a imagem original antes de tomar decisões. Uma expressão estimada não demonstra intenção, personalidade ou estado clínico.",
            "Full Analysis combines the implemented families in the chosen profile, subject to step and time limits. It does not mean every possible analysis from every model. Labels, OCR and expressions are fallible inferences: check the original image before making decisions. An estimated expression does not establish intent, personality or a clinical state.",
          ),
        ],
      },
    ],
    outcome: t(
      "Um resultado com resumo, cobertura, etapas, entradas resolvidas e geometrias, exportável em JSON/Markdown. A entrega ao datalake tem um status separado do processamento.",
      "A result containing summary, coverage, steps, resolved inputs and geometry, exportable as JSON/Markdown. Datalake delivery has a separate status from processing.",
    ),
    problems: [
      t(
        "Perfil facial indisponível: use o perfil Florence disponível ou consulte a administração; a existência do perfil na documentação não habilita a engine.",
        "Facial profile unavailable: use the available Florence profile or contact the administrator; documenting a profile does not enable its engine.",
      ),
      t(
        "Regiões vazias ou baixa cobertura: confira a etapa e a consulta selecionadas, o motivo de omissão e os limites informados. Para integrações, preserve Idempotency-Key ao repetir o mesmo pedido após perda de resposta.",
        "Empty regions or low coverage: check the selected step/query, the omission reason and reported limits. For integrations, retain Idempotency-Key when retrying the same request after a lost response.",
      ),
    ],
    actions: [
      { href: "/convert", label: t("Analisar uma imagem", "Analyze an image") },
      {
        href: "/jobs",
        label: t("Explorar minhas análises", "Explore my analyses"),
      },
    ],
  },
  "platform-datalakes": {
    goal: t(
      "Conecte AWS S3, MinIO, Google Cloud Storage ou Azure Blob Storage e entregue os resultados em um bucket controlado por você.",
      "Connect AWS S3, MinIO, Google Cloud Storage or Azure Blob Storage and deliver results to a bucket you control.",
    ),
    requirements: [
      t(
        "Credenciais do provedor com as permissões necessárias para listar/usar buckets e escrever objetos. Criar um bucket exige permissões adicionais. No Azure, bucket corresponde a container.",
        "Provider credentials with the permissions needed to list/use buckets and write objects. Creating a bucket requires additional permissions. In Azure, bucket means container.",
      ),
      t(
        "Endpoint/região para S3/MinIO, projeto e credencial Google para GCS, ou conta/credencial Azure, conforme os campos do provedor escolhido.",
        "S3/MinIO endpoint/region, Google project and credential for GCS, or Azure account/credential, as required by the selected provider fields.",
      ),
    ],
    parts: [
      {
        title: t(
          "Assistente Conexão → Buckets → Padrões → Revisão",
          "Connection → Buckets → Defaults → Review wizard",
        ),
        steps: [
          t(
            "Abra /datalakes e crie uma conexão. Na etapa Conexão, informe nome, provedor e credenciais. Use o endpoint correto do MinIO ou o da conta S3 compatível.",
            "Open /datalakes and add a connection. In Conexão, enter a name, provider and credentials. Use the correct MinIO endpoint or compatible S3 account endpoint.",
          ),
          t(
            "Em Buckets, carregue a lista e escolha os buckets permitidos, ou permita todos os acessíveis. A lista depende das permissões da conta; permitir todos não concede acesso adicional no provedor.",
            "In Buckets, load the list and choose allowed buckets, or allow all accessible buckets. Listing depends on account permissions; allowing all does not grant additional provider access.",
          ),
          t(
            "Para um destino novo, clique em Criar bucket agora. Confira o nome e a localização: GCS pede localização explícita; S3/MinIO usa a região da conexão; Azure cria um container privado. O bucket criado permanece no provedor mesmo se você cancelar o assistente.",
            "For a new destination, click Criar bucket agora. Check the name and location: GCS requires an explicit location; S3/MinIO uses the connection region; Azure creates a private container. The created bucket remains at the provider even if you cancel the wizard.",
          ),
          t(
            "Em Padrões, escolha bucket e pasta padrão. Deixe o bucket vazio para escolher por pedido. Configure a estratégia de particionamento, valores personalizados e exportação analítica, então confira Exemplo de destino.",
            "In Padrões, choose a default bucket and folder. Leave the bucket empty to choose per request. Configure partition strategy, custom values and analytical export, then review Exemplo de destino.",
          ),
          t(
            "Em Revisão, confirme provedor, buckets, padrão, estratégia, fuso e caminho antes de salvar. Use o teste da conexão para conferir acesso; salvar a configuração não prova que toda entrega futura terá sucesso.",
            "In Revisão, confirm the provider, buckets, defaults, strategy, time zone and path before saving. Use the connection test to check access; saving configuration does not prove every future delivery will succeed.",
          ),
        ],
      },
      {
        title: t(
          "Escolher o destino e conferir a entrega",
          "Choose a destination and verify delivery",
        ),
        steps: [
          t(
            "No envio de Full Analysis/rostos, abra Destino dos resultados: selecione conexão, bucket, pasta e valores de partição. Usar padrões da conexão restaura a seleção inicial. Nesta versão, o destino está ligado a Full Analysis e rostos, tanto na tela quanto na API. Documentos, áudio gravado e sessões live ainda não ligam esse destino ao processamento.",
            "When submitting Full Analysis/faces, open Destino dos resultados: select the connection, bucket, folder and partition values. Usar padrões da conexão restores the initial selection. In this version, destination delivery is connected to Full Analysis and faces, in both the screen and API. Documents, recorded audio and live sessions do not yet connect that destination to processing.",
          ),
          t(
            "Após o processamento, abra o job e consulte Entrega ao datalake. Confira status, bucket/caminho, layout e dataset quando houver. Resultados entregues e Ver arquivos confirmam os objetos exportados.",
            "After processing, open the job and inspect Entrega ao datalake. Check the status, bucket/path, layout and dataset when present. Resultados entregues and Ver arquivos confirm exported objects.",
          ),
          t(
            "Se a entrega falhar, corrija credenciais/acesso da conexão e use Tentar entrega novamente. Isso repete a exportação do resultado existente, preservando o caminho resolvido; não refaz a análise.",
            "If delivery fails, correct connection credentials/access and use Tentar entrega novamente. This retries export of the existing result and preserves the resolved path; it does not rerun analysis.",
          ),
        ],
      },
    ],
    outcome: t(
      "Resultados e metadados no bucket escolhido, com acompanhamento independente da entrega. Excluir um job ou uma conexão no Ingestify preserva os arquivos do bucket externo.",
      "Results and metadata in the chosen bucket, with independent delivery tracking. Deleting an Ingestify job or connection preserves files in the external bucket.",
    ),
    problems: [
      t(
        "Lista de buckets indisponível: verifique permissão de listagem e credenciais. Quando a tela permitir informar o nome manualmente, o bucket ainda deve existir e estar autorizado.",
        "Bucket listing unavailable: check list permissions and credentials. When the screen permits manually entering a name, the bucket must still exist and be authorized.",
      ),
      t(
        "Job concluído, entrega falhou: são estados separados. Leia o erro de entrega e teste a conexão antes de repetir somente a exportação.",
        "Job completed, delivery failed: these are separate states. Read the delivery error and test the connection before retrying only the export.",
      ),
    ],
    actions: [
      {
        href: "/datalakes",
        label: t("Configurar conexões", "Configure connections"),
      },
      {
        href: "/convert",
        label: t(
          "Enviar Full Analysis para um bucket",
          "Send Full Analysis to a bucket",
        ),
      },
    ],
  },
  "platform-partitioning": {
    goal: t(
      "Agrupe resultados do mesmo cliente em um layout de armazenamento consistente. Nesta versão, a entrega automática está ligada a imagens Full Analysis e rostos; exportar conversas para esse fluxo exige integração adicional.",
      "Group results for the same customer under a consistent storage layout. In this version, automatic delivery is connected to Full Analysis and faces images; exporting conversations into this flow requires additional integration.",
    ),
    requirements: [
      t(
        "Uma conexão de datalake e um identificador estável de cliente, por exemplo customer_id. Use o mesmo identificador em todos os pedidos daquele cliente, evitando nomes que mudam.",
        "A datalake connection and a stable customer identifier, such as customer_id. Use the same identifier in every request for that customer, avoiding names that change.",
      ),
    ],
    parts: [
      {
        title: t(
          "Configurar um layout por cliente",
          "Configure a customer layout",
        ),
        steps: [
          t(
            "Abra a conexão em /datalakes e vá a Padrões. Escolha Personalizada em Estratégia de particionamento. Adicione Campo personalizado e use a chave customer_id.",
            "Open the connection in /datalakes and go to Padrões. Choose Personalizada under Estratégia de particionamento. Add Campo personalizado and use the key customer_id.",
          ),
          t(
            "Adicione Data depois do cliente, se quiser dividir por mês/dia/hora. Use os botões Subir/Descer para definir a ordem dos campos no caminho. Configure o fuso, por exemplo America/Sao_Paulo.",
            "Add Data after the customer to split by month/day/hour. Use Subir/Descer to set field order in the path. Set the time zone, such as America/Sao_Paulo.",
          ),
          t(
            "Em Quando um valor estiver ausente, escolha Exigir preenchimento para evitar que clientes sem ID acabem na mesma partição. Se usar valor substituto, acompanhe essa partição como dado incompleto.",
            "Under Quando um valor estiver ausente, choose Exigir preenchimento to prevent customers without an ID from sharing a partition. If using a fallback value, track that partition as incomplete data.",
          ),
          t(
            "Selecione Arquivos + dataset JSONL em Exportação analítica. Revise Exemplo de destino e salve a conexão. Um valor padrão de customer_id só é apropriado para conexão dedicada a um cliente.",
            "Select Arquivos + dataset JSONL under Exportação analítica. Review Exemplo de destino and save the connection. A default customer_id value is only appropriate for a connection dedicated to one customer.",
          ),
          t(
            "No pedido, informe o valor real de customer_id em Valores dos campos personalizados. Na API, envie partition_values com essa chave no destino do datalake. Também é possível sobrescrever a estratégia por solicitação usando os campos documentados.",
            "In the request, enter the actual customer_id under Valores dos campos personalizados. Through the API, send partition_values containing that key in the datalake destination. You can also override the strategy per request using the documented fields.",
          ),
          t(
            "Confira a prévia e, depois do processamento, o caminho definitivo na entrega do job. A prévia usa a data atual; a entrega usa a data de criação do job e mantém o caminho em retries.",
            "Check the preview and, after processing, the final path in job delivery. The preview uses the current date; delivery uses the job creation date and keeps the path during retries.",
          ),
        ],
      },
      {
        title: t(
          "Consumir as conversas do cliente",
          "Consume a customer's conversations",
        ),
        paragraphs: [
          t(
            "JSONL produz um registro por job, com texto, metadados e resultado completo, em objetos próprios do dataset; não é um arquivo único que o Ingestify concatena continuamente. O esquema e o layout ajudam seu consumidor a ler as partições relevantes.",
            "JSONL produces one record per job, containing text, metadata and the full result, in separate dataset objects; it is not one file continuously appended by Ingestify. The schema and layout help your consumer read the relevant partitions.",
          ),
          t(
            "Seu agente ou ferramenta analítica pode ler registros da partição customer_id para reunir o histórico do cliente. A entrega automática de transcrições ainda não está conectada nesta versão: para agregar conversas, sua integração precisa buscar os resultados dos jobs e armazená-los com o mesmo identificador. O Ingestify não oferece ainda uma análise automática entre várias conversas ou memória conversacional consolidada.",
            "Your agent or analytics tool can read records in a customer_id partition to combine a customer's history. Automatic transcript delivery is not yet connected in this version: to aggregate conversations, your integration must retrieve job results and store them under the same identifier. Ingestify does not yet provide automatic analysis across conversations or consolidated conversational memory.",
          ),
          t(
            "Alterar a estratégia afeta somente novas solicitações e cria uma versão de layout própria. Não reorganiza objetos já exportados. Quem agrega histórico deve considerar as versões antigas e novas.",
            "Changing the strategy affects only new requests and creates its own layout version. It does not reorganize already exported objects. Consumers aggregating history must consider old and new versions.",
          ),
        ],
      },
    ],
    outcome: t(
      "Objetos organizados por dimensões controladas por você, com customer_id consistente e registros JSONL que uma aplicação pode reunir para análise.",
      "Objects organized by dimensions you control, with a consistent customer_id and JSONL records that an application can combine for analysis.",
    ),
    problems: [
      t(
        "Valor obrigatório ausente: informe customer_id no pedido ou corrija o padrão da conexão. Não remova a exigência apenas para ignorar o erro se isso misturar clientes.",
        "Missing required value: enter customer_id in the request or correct the connection default. Do not remove the requirement just to bypass the error if it would mix customers.",
      ),
      t(
        "Datas ou caminhos diferentes do esperado: confira fuso, granularidade, ordem dos campos, criação do job e versão de layout. Retry preserva o destino original.",
        "Unexpected dates or paths: check the time zone, granularity, field order, job creation time and layout version. Retry preserves the original destination.",
      ),
    ],
    actions: [
      {
        href: "/datalakes",
        label: t("Configurar particionamento", "Configure partitioning"),
      },
      {
        href: "/api-keys",
        label: t(
          "Preparar a integração do agente",
          "Prepare agent integration",
        ),
      },
    ],
  },
  "administration-overview": {
    goal: t(
      "Mantenha o processamento disponível e controle onde cada operação executa, quais limites se aplicam e quem pode alterar a instalação.",
      "Keep processing available and control where each operation runs, which limits apply and who can modify the installation.",
    ),
    requirements: [
      t(
        "Uma conta com permissão administrativa: o root (primeiro cadastro de uma instalação nova; veja GET /auth/setup), outro administrador de bootstrap ou um papel concedido em Admin → Acesso. Cada seção do Admin aparece só com a permissão correspondente; possuir uma API key de usuário não concede administração.",
        "An account with administrative permission: root (the first registration of a new installation; see GET /auth/setup), another bootstrap administrator or a role granted under Admin → Access. Each Admin section appears only with the matching permission; possessing a user API key does not grant administration.",
      ),
      t(
        "Conheça a infraestrutura local e as contas externas configuradas. Engines locais e Modal têm capacidades diferentes; cadastrar uma conta não habilita todas as features.",
        "Understand the local infrastructure and configured external accounts. Local and Modal engines have different capabilities; registering an account does not enable every feature.",
      ),
    ],
    parts: [
      {
        title: t("Preparar uma instalação", "Prepare an installation"),
        steps: [
          t(
            "Comece em /admin e confira /admin/status para diagnosticar serviços. Em /admin/engines, revise saúde, estado, capacidade e orçamento das engines disponíveis.",
            "Start at /admin and check /admin/status to diagnose services. In /admin/engines, review health, state, capacity and budget for available engines.",
          ),
          t(
            "Abra a engine para consultar features e operações permitidas. Use o guia Recursos das engines para conferir quais adapters e runtimes realmente atendem à operação desejada.",
            "Open an engine to inspect features and allowed operations. Use the Engine features guide to check which adapters and runtimes actually support the desired operation.",
          ),
          t(
            "Em /admin/execution-profiles, confira perfis e publicações antes de vincular uma configuração. Perfis controlam o runtime; publicar não migra automaticamente todas as engines.",
            "In /admin/execution-profiles, inspect profiles and publications before binding a configuration. Profiles control the runtime; publishing does not automatically migrate every engine.",
          ),
          t(
            "Em /admin/routing, confira o destino por feature. Em /admin/gpus, confira GPU/capacidade. Uma rota configurada só executa quando sua engine e workers atendem aos requisitos.",
            "In /admin/routing, check destinations by feature. In /admin/gpus, check GPU/capacity. A configured route only executes when its engine and workers meet the requirements.",
          ),
          t(
            "Em /admin/access (Admin → Acesso), conceda papéis de plataforma (platform_admin, platform_operator, platform_auditor, remote_engine_user) e de engines, revise políticas e restrições. As configurações da plataforma (variáveis de ambiente como IAM_MODE e ROOT_SETUP_TOKEN) definem quando os bindings decidem.",
            "In /admin/access (Admin → Access), grant platform roles (platform_admin, platform_operator, platform_auditor, remote_engine_user) and engines roles, and review policies and constraints. Platform settings (environment variables such as IAM_MODE and ROOT_SETUP_TOKEN) define when bindings decide.",
          ),
          t(
            "Faça um processamento pequeno de cada operação necessária e confira resultado e entrega. Para operações de engine, revise planos e confirmações do guia específico antes de aplicar mudanças.",
            "Run a small processing job for each required operation and check the result and delivery. For engine operations, review plans and confirmations in the specific guide before applying changes.",
          ),
        ],
      },
    ],
    outcome: t(
      "Features encaminhadas para engines compatíveis, perfis e acesso definidos, e diagnóstico de capacidade. Os guias abaixo detalham contratos, comandos, planos e requisitos de cada área.",
      "Features routed to compatible engines, defined profiles and access, and capacity diagnostics. The guides below detail contracts, commands, plans and requirements for each area.",
    ),
    problems: [
      t(
        "Jobs não saem da fila: consulte saúde, workers, capacidade, orçamento e rota da feature. Uma engine pausada ou sem capacidade não é corrigida pelo usuário reenviando arquivos.",
        "Jobs remain queued: inspect health, workers, capacity, budget and feature routing. A paused engine or lack of capacity is not fixed by a user resubmitting files.",
      ),
      t(
        "Operação recusada: leia code, message e next_steps do erro e confira papel/permissão, política de engines e requisitos do plano. Não interprete um adapter configurável como suporte ativo a qualquer operação.",
        "Operation denied: read the error code, message and next_steps, then check the role/permission, engines policy and plan requirements. Do not interpret a configurable adapter as active support for every operation.",
      ),
    ],
    actions: [
      {
        href: "/admin",
        label: t("Abrir administração", "Open administration"),
      },
      {
        href: "/admin/engines",
        label: t("Conferir engines", "Inspect engines"),
      },
    ],
  },
};

export function isPlatformGuide(topic: string) {
  return topic in guides;
}

export function PlatformGuide({
  topic,
  lang,
}: {
  topic: string;
  lang: DocsLang;
}) {
  const guide = guides[topic];
  const title = DOCS_TOPICS.find((item) => item.slug === topic)?.title[lang];
  const pt = lang === "pt";
  return (
    <article
      id={topic}
      className="scroll-mt-24 space-y-6"
      data-platform-guide={topic}
    >
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="leading-relaxed text-muted-foreground">
        {guide.goal[lang]}
      </p>
      <div className="flex flex-wrap gap-3">
        {guide.actions.map((action) => (
          <Link
            key={action.href}
            href={action.href}
            className="rounded-md border px-4 py-2 text-sm font-medium text-primary hover:bg-muted"
          >
            {action.label[lang]}
          </Link>
        ))}
      </div>
      <section className="space-y-3 rounded-lg border bg-muted/30 p-4">
        <h2 className="text-lg font-semibold">
          {pt ? "Antes de começar" : "Before you start"}
        </h2>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
          {guide.requirements.map((text, index) => (
            <li key={index}>{text[lang]}</li>
          ))}
        </ul>
      </section>
      {guide.parts.map((part, index) => (
        <section key={index} className="space-y-3">
          <h2 className="text-xl font-semibold">{part.title[lang]}</h2>
          {part.paragraphs?.map((text, i) => (
            <p key={i} className="leading-relaxed text-muted-foreground">
              {text[lang]}
            </p>
          ))}
          {part.steps && (
            <ol className="list-decimal space-y-3 pl-6 leading-relaxed text-muted-foreground">
              {part.steps.map((text, i) => (
                <li key={i} className="pl-1">
                  {text[lang]}
                </li>
              ))}
            </ol>
          )}
        </section>
      ))}
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">
          {pt ? "Resultado esperado" : "Expected outcome"}
        </h2>
        <p className="leading-relaxed text-muted-foreground">
          {guide.outcome[lang]}
        </p>
      </section>
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">
          {pt ? "Problemas comuns" : "Common problems"}
        </h2>
        <ul className="list-disc space-y-3 pl-5 leading-relaxed text-muted-foreground">
          {guide.problems.map((text, i) => (
            <li key={i}>{text[lang]}</li>
          ))}
        </ul>
      </section>
      {topic === "platform-start" && (
        <p className="text-sm text-muted-foreground">
          {pt ? "Próximo passo:" : "Next step:"}{" "}
          <Link
            href={docsHref("platform-projects-jobs", lang)}
            className="text-primary underline"
          >
            {pt
              ? "organizar o histórico por projeto e pasta"
              : "organize history by project and folder"}
          </Link>
          .
        </p>
      )}
    </article>
  );
}
