"""Bilingual texts of the API refusals that are not engine-control/IAM guidance.

``API_CATALOG[code] = ({"en": template, "pt": template}, next_steps)`` has the same
shape as ``error_catalog.CATALOG``, which merges it at import. Portuguese keeps the
wording the API had before P-13; English is written natively. ``{params}`` are
named and must be identical in both languages (a test checks it).
"""

API_CATALOG = {
    # --- job creation (/upload, /convert, /transcribe) -------------------------
    "DATABASE_UNAVAILABLE": (
        {
            "en": "The database is unavailable; try again in a moment.",
            "pt": "Banco de dados indisponível; tente de novo",
        },
        ["retry"],
    ),
    "QUEUE_UNAVAILABLE": (
        {
            "en": "The processing queue is unavailable right now. Try again in a moment.",
            "pt": "Sistema de processamento indisponível",
        },
        ["retry"],
    ),
    "SEARCH_UNAVAILABLE": (
        {
            "en": "Search is unavailable right now. Try again in a moment.",
            "pt": "A busca está indisponível no momento. Tente novamente em instantes.",
        },
        ["retry"],
    ),
    "JOB_CREATE_FAILED": (
        {"en": "The job could not be created.", "pt": "Erro ao criar job"},
        ["retry"],
    ),
    "FILE_TOO_LARGE": (
        {
            "en": "The file is too large. Maximum size: {max_size_mb} MB.",
            "pt": "Arquivo muito grande. Máximo: {max_size_mb}MB",
        },
        ["fix_input"],
    ),
    "FILE_EMPTY": (
        {"en": "The uploaded file is empty.", "pt": "Arquivo enviado está vazio"},
        ["fix_input"],
    ),
    "INVALID_FILE_FORMAT": (
        {
            "en": "The file content is not {kind} (the signature is missing at the start of the file).",
            "pt": "O conteúdo do arquivo não é {kind} (assinatura ausente no início do arquivo)",
        },
        ["fix_input"],
    ),
    "TRANSCRIPTION_DISABLED": (
        {
            "en": "Audio transcription is turned off on this server.",
            "pt": "A transcrição de áudio está desligada neste servidor.",
        },
        [],
    ),
    "INVALID_OUTPUT_FORMAT": (
        {
            "en": "Invalid output_format: {output_format}. Use one of: {allowed}.",
            "pt": "output_format inválido: {output_format}. Use: {allowed}",
        },
        ["fix_input"],
    ),
    "UNSUPPORTED_MEDIA_FORMAT": (
        {
            "en": (
                "Unsupported format. MIME type: {mime_type}, extension: {extension}. "
                "Audio: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC. "
                "Video: MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP."
            ),
            "pt": (
                "Formato não suportado. MIME type: {mime_type}, Extensão: {extension}. "
                "Áudio: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC. "
                "Vídeo: MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP"
            ),
        },
        ["fix_input"],
    ),
    "INVALID_SOURCE_TYPE": (
        {
            "en": "Invalid source_type: {source_type}. Use one of: file, url, gdrive or dropbox.",
            "pt": "source_type inválido: {source_type}. Use: file, url, gdrive ou dropbox",
        },
        ["fix_input"],
    ),
    "FILE_REQUIRED": (
        {
            "en": "A file is required when source_type=file.",
            "pt": "Arquivo é obrigatório para source_type=file",
        },
        ["fix_input"],
    ),
    "SOURCE_REQUIRED": (
        {
            "en": "source is required when source_type={source_type}.",
            "pt": "source é obrigatório para source_type={source_type}",
        },
        ["fix_input"],
    ),
    "SOURCE_TOKEN_REQUIRED": (
        {
            "en": "The X-Source-Token header (the provider's access token) is required for this source.",
            "pt": "O header X-Source-Token (token do provedor) é obrigatório para esta fonte",
        },
        ["fix_input"],
    ),
    "INTERNAL_ERROR": (
        {"en": "Internal server error", "pt": "Erro interno do servidor"},
        ["retry"],
    ),
    # --- projects, folders and upload locations ---------------------------------
    "PROJECT_LIMIT": (
        {
            "en": "The limit of {limit} projects has been reached.",
            "pt": "Limite de {limit} projetos atingido",
        },
        [],
    ),
    "FOLDER_LIMIT": (
        {
            "en": "The limit of {limit} folders in this project has been reached.",
            "pt": "Limite de {limit} pastas atingido neste projeto",
        },
        [],
    ),
    "PROJECT_CREATE_FAILED": (
        {
            "en": "The project could not be created right now; try again.",
            "pt": "Não foi possível criar o projeto agora; tente de novo",
        },
        ["retry"],
    ),
    "FOLDER_CREATE_FAILED": (
        {
            "en": "The folder could not be created right now; try again.",
            "pt": "Não foi possível criar a pasta agora; tente de novo",
        },
        ["retry"],
    ),
    "PROJECT_NAME_EMPTY": (
        {"en": "The project name is empty.", "pt": "Nome do projeto vazio"},
        ["fix_input"],
    ),
    "FOLDER_NAME_EMPTY": (
        {"en": "The folder name is empty.", "pt": "Nome da pasta vazio"},
        ["fix_input"],
    ),
    "PROJECT_NAME_CONTROL_CHARS": (
        {
            "en": "The project name contains control characters.",
            "pt": "Nome do projeto contém caracteres de controle",
        },
        ["fix_input"],
    ),
    "FOLDER_NAME_CONTROL_CHARS": (
        {
            "en": "The folder name contains control characters.",
            "pt": "Nome da pasta contém caracteres de controle",
        },
        ["fix_input"],
    ),
    "FOLDER_NAME_SLASH": (
        {
            "en": "A folder name cannot contain '/'.",
            "pt": "Nome da pasta não pode conter '/'",
        },
        ["fix_input"],
    ),
    "NAME_TOO_LONG": (
        {
            "en": "The name is too long (maximum {max} characters).",
            "pt": "Nome muito longo (máximo {max} caracteres)",
        },
        ["fix_input"],
    ),
    "NAME_KEY_TOO_LONG": (
        {
            "en": "The name is too long once normalized (maximum {max} characters).",
            "pt": "Nome muito longo depois de normalizado (máximo {max} caracteres)",
        },
        ["fix_input"],
    ),
    "PROJECT_REQUIRED": (
        {
            "en": (
                "Say which project the upload belongs to: the 'project' field (a name; it is "
                "created if it does not exist) or 'project_id'. Example: curl -H \"X-API-Key: ...\" "
                "-F \"file=@lecture.mp3\" -F \"project=Lectures\" .../transcribe\n"
                "To avoid sending the project every time, bind the API key to a project at /api-keys."
            ),
            "pt": (
                "Informe o projeto do upload: campo 'project' (nome; é criado se não existir) ou "
                "'project_id'. Exemplo: curl -H \"X-API-Key: ...\" -F \"file=@arquivo.mp3\" "
                "-F \"project=Aulas\" .../transcribe\n"
                "Para não precisar enviar o projeto, vincule a API key a um projeto em /api-keys."
            ),
        },
        ["fix_input"],
    ),
    "KEY_PROJECT_GONE": (
        {
            "en": (
                "The project bound to this API key no longer exists. Send the 'project' field "
                "(a name; it is created if it does not exist) or 'project_id', or bind the key "
                "to another project at /api-keys."
            ),
            "pt": (
                "O projeto vinculado a esta API key não existe mais. Informe o campo 'project' "
                "(nome; é criado se não existir) ou 'project_id', ou vincule a key a outro projeto em /api-keys."
            ),
        },
        ["fix_input"],
    ),
    "PROJECT_ARCHIVED": (
        {"en": "The project is archived.", "pt": "Projeto arquivado"},
        [],
    ),
    "FOLDER_NOT_IN_PROJECT": (
        {
            "en": "The folder does not belong to the project given.",
            "pt": "A pasta não pertence ao projeto informado",
        },
        ["fix_input"],
    ),
    "LOCATION_PROJECT_AND_ID": (
        {
            "en": "Send either 'project' or 'project_id', not both.",
            "pt": "Envie 'project' ou 'project_id', não os dois",
        },
        ["fix_input"],
    ),
    "LOCATION_FOLDER_AND_ID": (
        {
            "en": "Send either 'folder' or 'folder_id', not both.",
            "pt": "Envie 'folder' ou 'folder_id', não os dois",
        },
        ["fix_input"],
    ),
    # --- completion webhooks (callback_url) ------------------------------------------
    "CALLBACK_URL_EMPTY": (
        {"en": "callback_url is empty.", "pt": "callback_url está vazio."},
        ["fix_input"],
    ),
    "CALLBACK_URL_TOO_LONG": (
        {
            "en": "callback_url is longer than {max} characters.",
            "pt": "callback_url tem mais de {max} caracteres.",
        },
        ["fix_input"],
    ),
    "CALLBACK_URL_INVALID": (
        {"en": "callback_url is not a valid URL.", "pt": "callback_url não é uma URL válida."},
        ["fix_input"],
    ),
    "CALLBACK_URL_SCHEME": (
        {"en": "callback_url must use https.", "pt": "callback_url deve usar https."},
        ["fix_input"],
    ),
    "CALLBACK_URL_NO_HOST": (
        {"en": "callback_url has no host.", "pt": "callback_url não tem host."},
        ["fix_input"],
    ),
    "CALLBACK_URL_CREDENTIALS": (
        {
            "en": "callback_url must not contain credentials.",
            "pt": "callback_url não pode conter credenciais.",
        },
        ["fix_input"],
    ),
    "CALLBACK_URL_PRIVATE_ADDRESS": (
        {
            "en": "callback_url must not point to a private or reserved address.",
            "pt": "callback_url não pode apontar para um endereço privado ou reservado.",
        },
        ["fix_input"],
    ),
    "CALLBACK_URL_NOT_PUBLIC_HOST": (
        {
            "en": "callback_url must point to a public host name.",
            "pt": "callback_url deve apontar para um nome de host público.",
        },
        ["fix_input"],
    ),
    # --- tags --------------------------------------------------------------------
    "TAG_TOO_LONG": (
        {
            "en": "Tag too long (maximum {max} characters): {tag}",
            "pt": "Tag muito longa (máximo {max} caracteres): {tag}",
        },
        ["fix_input"],
    ),
    "TAGS_TOO_MANY": (
        {
            "en": "A job can have at most {max} tags ({count} sent).",
            "pt": "Máximo de {max} tags por job ({count} enviadas)",
        },
        ["fix_input"],
    ),
    "TAGS_TOO_MANY_TOTAL": (
        {
            "en": "A job can have at most {max} tags ({count} in total).",
            "pt": "Máximo de {max} tags por job ({count} no total)",
        },
        ["fix_input"],
    ),
    # --- not found (text 404s that do not reveal what exists) -----------------------
    "JOB_NOT_FOUND": (
        {"en": "Job not found", "pt": "Job não encontrado"},
        [],
    ),
    "PROJECT_NOT_FOUND_404": (
        {"en": "Project not found", "pt": "Projeto não encontrado"},
        [],
    ),
    "FOLDER_NOT_FOUND_404": (
        {"en": "Folder not found", "pt": "Pasta não encontrada"},
        [],
    ),
    "API_KEY_NOT_FOUND": (
        {"en": "API key not found", "pt": "API key não encontrada"},
        [],
    ),
    # --- live transcription ---------------------------------------------------------
    "LIVE_SESSION_NOT_FOUND": (
        {"en": "Session not found", "pt": "Sessão não encontrada"},
        [],
    ),
    "LIVE_DISABLED": (
        {
            "en": "Live transcription is turned off on this server.",
            "pt": "A transcrição ao vivo está desligada neste servidor.",
        },
        [],
    ),
    "LIVE_NOT_READY": (
        {
            "en": "The live transcription service is not available right now. Try again in a moment.",
            "pt": "O serviço de transcrição ao vivo não está disponível agora. Tente de novo em instantes.",
        },
        ["retry"],
    ),
    "LIVE_CAPACITY_FULL": (
        {
            "en": "All live transcription slots are in use. Try again in a moment.",
            "pt": "Todas as vagas de transcrição ao vivo estão em uso. Tente de novo em instantes.",
        },
        ["retry"],
    ),
    "LIVE_DIARIZATION_NOT_READY": (
        {
            "en": "Live speaker identification is not available right now.",
            "pt": "A identificação de falantes ao vivo não está disponível agora.",
        },
        ["retry"],
    ),
}
