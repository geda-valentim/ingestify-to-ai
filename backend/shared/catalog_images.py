"""Bilingual texts of the datalake and image (/images) refusals (P-13, slice 3).

Same shape as ``catalog_api.API_CATALOG`` (``code -> ({"en", "pt"}, next_steps)``),
merged into ``error_catalog.CATALOG`` at import. Portuguese keeps the wording the
routes had; where the text was already English (vision worker and API-side image
checks) the English stays native and Portuguese is new. ``{params}`` are named and
identical in both languages.

Some keys are *message keys*, not envelope codes: ``/images`` keeps its historical
``error_code`` values (INVALID_VISION_OPTIONS, INVALID_BASE64, ...) and picks the
text with ``key=``.
"""

IMAGES_CATALOG = {
    # --- datalake connections ---------------------------------------------------------
    "DATALAKE_NOT_FOUND": ({"en": "Connection not found", "pt": "Conexão não encontrada"}, []),
    "DATALAKE_PROVIDER_IMMUTABLE": (
        {"en": "The connection's provider cannot be changed.", "pt": "O provedor da conexão não pode ser alterado"},
        ["fix_input"],
    ),
    "DATALAKE_CREDENTIALS_REQUIRED": (
        {"en": "Provide the provider credentials.", "pt": "Informe as credenciais do provedor"},
        ["fix_input"],
    ),
    "DATALAKE_CREDENTIALS_INCOMPLETE": (
        {"en": "Provide all of the provider's credentials.", "pt": "Informe todas as credenciais do provedor"},
        ["fix_input"],
    ),
    "DATALAKE_ENDPOINT_REQUIRED": (
        {"en": "Provide the MinIO endpoint.", "pt": "Informe o endpoint do MinIO"},
        ["fix_input"],
    ),
    "DATALAKE_GCS_JSON_INVALID": (
        {
            "en": "Provide a valid Google service account JSON.",
            "pt": "Informe um JSON de conta de serviço válido do Google",
        },
        ["fix_input"],
    ),
    "DATALAKE_BUCKET_INACCESSIBLE": (
        {"en": "Bucket not found or not accessible.", "pt": "Bucket não encontrado ou sem acesso"},
        ["fix_input"],
    ),
    "DATALAKE_BUCKET_NOT_ALLOWED": (
        {
            "en": "This bucket is not allowed for this connection.",
            "pt": "Bucket não permitido para esta conexão",
        },
        ["fix_input"],
    ),
    "DATALAKE_DISABLED": ({"en": "Connection disabled", "pt": "Conexão desativada"}, []),
    "DATALAKE_JOB_HAS_DESTINATION": (
        {"en": "This job already has another destination.", "pt": "Este job já possui outro destino"},
        [],
    ),
    "DATALAKE_NAME_REQUIRED": ({"en": "Provide a name.", "pt": "Informe um nome"}, ["fix_input"]),
    "DATALAKE_PREFIX_INVALID": ({"en": "Invalid folder.", "pt": "Pasta inválida"}, ["fix_input"]),
    "DATALAKE_BUCKET_INVALID": ({"en": "Invalid bucket.", "pt": "Bucket inválido"}, ["fix_input"]),
    "DATALAKE_ENDPOINT_INVALID": (
        {
            "en": "Provide an HTTP(S) endpoint without credentials, parameters or a path.",
            "pt": "Informe um endpoint HTTP(S) sem credenciais, parâmetros ou caminho",
        },
        ["fix_input"],
    ),
    "DATALAKE_DEFAULT_BUCKET_NOT_ALLOWED": (
        {
            "en": "The default bucket must be in the list of allowed buckets.",
            "pt": "O bucket padrão deve estar na lista de buckets permitidos",
        },
        ["fix_input"],
    ),
    "DATALAKE_IN_USE": (
        {
            "en": "This connection is linked to jobs. Disable it to stop new requests.",
            "pt": "Esta conexão está vinculada a jobs. Desative-a para impedir novas solicitações.",
        },
        [],
    ),
    "DATALAKE_DISCOVER_FAILED": (
        {
            "en": "Could not list the buckets. Check the connection or provide a bucket to validate its access.",
            "pt": "Não foi possível listar os buckets. Verifique a conexão ou informe um bucket para validar seu acesso.",
        },
        ["retry"],
    ),
    "DATALAKE_BUCKETS_UNAVAILABLE": (
        {
            "en": "Could not list the buckets. Check the credentials or configure the allowed buckets.",
            "pt": "Não foi possível listar os buckets. Verifique as credenciais ou configure os buckets permitidos.",
        },
        ["retry"],
    ),
    "DATALAKE_CONNECTION_UNREACHABLE": (
        {
            "en": "Could not reach the connection. Check the credentials, the endpoint and the permissions.",
            "pt": "Não foi possível acessar a conexão. Verifique as credenciais, o endpoint e as permissões.",
        },
        ["retry"],
    ),
    "DATALAKE_OBJECTS_UNAVAILABLE": (
        {
            "en": "Could not list the files in this bucket.",
            "pt": "Não foi possível listar os arquivos deste bucket",
        },
        ["retry"],
    ),
    "DATALAKE_DESTINATION_UNREACHABLE": (
        {
            "en": "Could not reach the destination bucket.",
            "pt": "Não foi possível acessar o bucket de destino",
        },
        ["retry"],
    ),
    "DATALAKE_DESTINATION_INVALID": (
        {
            "en": "Provide a connection, an allowed bucket and a valid folder.",
            "pt": "Informe uma conexão, um bucket permitido e uma pasta válida",
        },
        ["fix_input"],
    ),
    "DATALAKE_DESTINATION_REJECTED": (
        {
            "en": "Invalid destination or disabled connection.",
            "pt": "Destino inválido ou conexão desativada",
        },
        ["fix_input"],
    ),
    "DATALAKE_BUCKET_NAME_INVALID": (
        {
            "en": "Invalid name for this provider. Use 3 to 63 lowercase letters, digits and hyphens, starting and ending with a letter or digit.",
            "pt": "Nome inválido para o provedor. Use de 3 a 63 letras minúsculas, números e hífens, começando e terminando com letra ou número.",
        },
        ["fix_input"],
    ),
    "DATALAKE_BUCKET_REGION_MISMATCH": (
        {
            "en": "Use the region configured on the connection; on Azure, the container uses the account's region.",
            "pt": "Use a região configurada na conexão; no Azure, o container usa a região da conta.",
        },
        ["fix_input"],
    ),
    "DATALAKE_BUCKET_EXISTS": (
        {
            "en": "This bucket already exists. Use 'Check another bucket' to select it.",
            "pt": "Este bucket já existe. Use ‘Verificar outro bucket’ para selecioná-lo.",
        },
        [],
    ),
    "DATALAKE_BUCKET_NAME_TAKEN": (
        {
            "en": "Name already in use. Choose another name or check the existing bucket.",
            "pt": "Nome já utilizado. Escolha outro nome ou verifique o bucket existente.",
        },
        ["fix_input"],
    ),
    "DATALAKE_BUCKET_FORBIDDEN": (
        {
            "en": "The account is not allowed to check or create this bucket. Check the credentials and permissions at the provider.",
            "pt": "A conta não tem permissão para verificar ou criar este bucket. Verifique as credenciais e permissões no provedor.",
        },
        [],
    ),
    "DATALAKE_BUCKET_CREATE_UNCONFIRMED": (
        {
            "en": "Could not confirm the creation. Check the bucket name at the provider before trying again.",
            "pt": "Não foi possível confirmar a criação. Verifique o nome do bucket no provedor antes de tentar novamente.",
        },
        ["retry"],
    ),
    "DATALAKE_DELIVERY_FAILED": (
        {
            "en": "Could not deliver to the bucket. Check the connection and the permissions and try again.",
            "pt": "Não foi possível entregar ao bucket. Verifique a conexão e as permissões e tente novamente.",
        },
        ["retry"],
    ),
    "DATALAKE_JOB_NOT_COMPLETED": (
        {"en": "Wait for the job to finish.", "pt": "Aguarde a conclusão do job"},
        ["retry"],
    ),
    "DATALAKE_DESTINATION_MISSING": (
        {"en": "Destination not found", "pt": "Destino não encontrado"},
        [],
    ),
    # --- datalake partitioning ------------------------------------------------------------
    "PARTITION_CUSTOM_KEY_RESERVED": (
        {
            "en": "Choose a unique custom key that does not use a reserved name.",
            "pt": "Escolha uma chave personalizada única, sem usar nomes reservados",
        },
        ["fix_input"],
    ),
    "PARTITION_FIELD_KEY_NAME": (
        {
            "en": "The key of a job field must keep its name.",
            "pt": "A chave de um campo do job deve manter seu nome",
        },
        ["fix_input"],
    ),
    "PARTITION_TIMEZONE_INVALID": (
        {"en": "Provide a valid IANA time zone.", "pt": "Informe um fuso horário IANA válido"},
        ["fix_input"],
    ),
    "PARTITION_SUBSTITUTE_INVALID": (
        {"en": "Provide a valid substitute value.", "pt": "Informe um valor substituto válido"},
        ["fix_input"],
    ),
    "PARTITION_FIELDS_REQUIRED": (
        {
            "en": "Select at least one partitioning field.",
            "pt": "Selecione ao menos um campo de particionamento",
        },
        ["fix_input"],
    ),
    "PARTITION_KEYS_DUPLICATE": (
        {
            "en": "Partitioning keys cannot repeat.",
            "pt": "As chaves de particionamento não podem se repetir",
        },
        ["fix_input"],
    ),
    "PARTITION_KEYS_TOO_MANY": (
        {
            "en": "Use up to 10 partitioning keys, including year, month, day and hour.",
            "pt": "Use até 10 chaves de particionamento, incluindo ano, mês, dia e hora",
        },
        ["fix_input"],
    ),
    "PARTITION_CUSTOM_TOO_MANY": (
        {"en": "Provide up to 20 custom fields.", "pt": "Informe até 20 campos personalizados"},
        ["fix_input"],
    ),
    "PARTITION_CUSTOM_KEY_INVALID": (
        {
            "en": "Invalid or reserved custom key.",
            "pt": "Chave personalizada inválida ou reservada",
        },
        ["fix_input"],
    ),
    "PARTITION_CUSTOM_VALUE_INVALID": (
        {
            "en": "Invalid custom value, or longer than 128 characters.",
            "pt": "Valor personalizado inválido ou maior que 128 caracteres",
        },
        ["fix_input"],
    ),
    "PARTITION_REQUIRED_FIELD_MISSING": (
        {
            "en": "Fill in the required partitioning field: {key}",
            "pt": "Preencha o campo obrigatório de particionamento: {key}",
        },
        ["fix_input"],
    ),
    "PARTITION_PATH_TOO_LONG": (
        {
            "en": "The full path exceeds 1,024 bytes. Shorten the folder or the custom fields.",
            "pt": "O caminho completo excede 1.024 bytes. Reduza a pasta ou os campos personalizados.",
        },
        ["fix_input"],
    ),
    # --- /images: the envelope keeps its historical error_code values ---------------------
    "VISION_DISABLED": (
        {
            "en": "Image description is currently disabled (set ENABLE_IMAGE_DESCRIPTION=true to enable).",
            "pt": "A descrição de imagens está desativada neste servidor (defina ENABLE_IMAGE_DESCRIPTION=true para ativá-la).",
        },
        [],
    ),
    "VISION_NO_WORKER": (
        {
            "en": "no vision worker heartbeat in the last {seconds}s (no worker is consuming the vision queue)",
            "pt": "nenhum heartbeat do worker de visão nos últimos {seconds}s (nenhum worker consome a fila de visão)",
        },
        [],
    ),
    "VISION_HEARTBEAT_UNREADABLE": (
        {
            "en": "could not read the vision worker heartbeat: {error}",
            "pt": "não foi possível ler o heartbeat do worker de visão: {error}",
        },
        [],
    ),
    "INVALID_VISION_OPTIONS": ({"en": "{detail}", "pt": "{detail}"}, ["fix_input"]),
    "IMAGE_MODE_INVALID": (
        {"en": "mode must be single or full.", "pt": "mode deve ser single ou full"},
        ["fix_input"],
    ),
    "IMAGE_FIELDS_INCOMPATIBLE_FULL": (
        {
            "en": "Fields incompatible with mode=full: {fields}",
            "pt": "Campos incompatíveis com mode=full: {fields}",
        },
        ["fix_input"],
    ),
    "IMAGE_OPTIONS_REQUIRE_FULL": (
        {
            "en": "full_options/datalake require mode=full.",
            "pt": "full_options/datalake exigem mode=full",
        },
        ["fix_input"],
    ),
    "UNSUPPORTED_CAPTION_TASK": (
        {
            "en": "Invalid task: {task}. Accepted: <MORE_DETAILED_CAPTION>, <DETAILED_CAPTION>, <CAPTION>.",
            "pt": "task inválido: {task}. Aceitos: <MORE_DETAILED_CAPTION>, <DETAILED_CAPTION>, <CAPTION>.",
        },
        ["fix_input"],
    ),
    "INVALID_LOCATION": ({"en": "{detail}", "pt": "{detail}"}, ["fix_input"]),
    "JOB_PERSISTENCE_UNAVAILABLE": (
        {
            "en": "The job and its configuration could not be saved. Try again.",
            "pt": "Não foi possível salvar o job e sua configuração. Tente novamente.",
        },
        ["retry"],
    ),
    "VISION_ERROR": ({"en": "Vision inference failed.", "pt": "A inferência de visão falhou."}, []),
    "VISION_INFERENCE_FAILED": (
        {
            "en": "Vision inference failed. Check the vision worker logs and job {job_id} for the full error.",
            "pt": "A inferência de visão falhou. Consulte os logs do worker de visão e o job {job_id} para o erro completo.",
        },
        [],
    ),
    "VISION_RESULT_INCOMPLETE": (
        {
            "en": "The vision worker returned an incomplete result (missing: {missing}).",
            "pt": "O worker de visão devolveu um resultado incompleto (faltando: {missing}).",
        },
        [],
    ),
    "VISION_IMAGE_WRITE_FAILED": (
        {
            "en": "Could not write the image for processing: {error}",
            "pt": "Não foi possível gravar a imagem para processamento: {error}",
        },
        ["retry"],
    ),
    "VISION_ENGINE_UNAVAILABLE": (
        {
            "en": "No vision engine can take this request right now. Try again in a moment.",
            "pt": "Nenhum motor de visão pode atender agora. Tente de novo em instantes.",
        },
        ["retry"],
    ),
    "CELERY_UNAVAILABLE": (
        {
            "en": "The processing system is unavailable.",
            "pt": "Sistema de processamento indisponível",
        },
        ["retry"],
    ),
    "VISION_TASKS_UNAVAILABLE": (
        {
            "en": "The processing system is unavailable: the vision tasks could not be loaded. Check that the vision worker is installed and running.",
            "pt": "Sistema de processamento indisponível: as tasks de visão não puderam ser carregadas. Verifique se o worker de visão está instalado e rodando.",
        },
        ["retry"],
    ),
    "VISION_ENQUEUE_FAILED": (
        {
            "en": "Could not enqueue the vision job: {error}",
            "pt": "Não foi possível enfileirar o job de visão: {error}",
        },
        ["retry"],
    ),
    "VISION_TIMEOUT": (
        {
            "en": "The description was not ready within {seconds}s. The job keeps processing.",
            "pt": "A descrição não ficou pronta em {seconds}s. O job continua processando.",
        },
        ["retry"],
    ),
    "VISION_TIMEOUT_FULL": (
        {
            "en": "The image analysis is still processing.",
            "pt": "Análise da imagem continua processando",
        },
        ["retry"],
    ),
    "IMAGE_ANALYSIS_QUEUED": (
        {"en": "Image analysis queued", "pt": "Análise de imagem enfileirada"},
        [],
    ),
    "IMAGE_FULL_ANALYSIS_QUEUED": (
        {"en": "Image analysis queued", "pt": "Análise da imagem enfileirada"},
        [],
    ),
    "FULL_ANALYSIS_NOT_FOUND": (
        {"en": "Full Analysis not found", "pt": "Full Analysis não encontrada"},
        [],
    ),
    "IMAGE_JOB_DELETED": (
        {
            "en": "Job deleted; use a new Idempotency-Key for another request.",
            "pt": "Job excluído; use nova Idempotency-Key para outra solicitação",
        },
        ["fix_input"],
    ),
    "IMAGE_IDEMPOTENCY_KEY_REUSED": (
        {
            "en": "Idempotency-Key already used with another request.",
            "pt": "Idempotency-Key já utilizada com outra solicitação",
        },
        ["fix_input"],
    ),
    "IMAGE_IDEMPOTENCY_KEY_REQUIRED": (
        {
            "en": "Idempotency-Key is required for composite analysis (1 to 128 characters).",
            "pt": "Idempotency-Key é obrigatória para análise composta (1..128 caracteres)",
        },
        ["fix_input"],
    ),
    "FLORENCE_NOT_READY": (
        {
            "en": "Florence is not ready for Full Analysis v2.",
            "pt": "Florence não está pronto para Full Analysis v2",
        },
        ["retry"],
    ),
    "IMAGE_SUBMISSION_CONFLICT": (
        {
            "en": "Conflict while preserving the request; try again.",
            "pt": "Conflito ao preservar a solicitação; tente novamente",
        },
        ["retry"],
    ),
    "IMAGE_PERSIST_FAILED": (
        {
            "en": "Could not preserve the image and its configuration.",
            "pt": "Não foi possível preservar a imagem e sua configuração",
        },
        ["retry"],
    ),
    "FACE_UNAVAILABLE": (
        {
            "en": "The requested facial stages are not available.",
            "pt": "As etapas faciais solicitadas não estão disponíveis",
        },
        ["retry"],
    ),
    "FACE_UPLOAD_FIELDS_INVALID": (
        {
            "en": "Unknown or repeated fields in the facial upload.",
            "pt": "Campos desconhecidos ou repetidos no upload facial",
        },
        ["fix_input"],
    ),
    "FACE_REQUEST_INVALID": (
        {"en": "Invalid image, options or tags.", "pt": "Imagem/opções/tags inválidas"},
        ["fix_input"],
    ),
    # --- image checks made by the API (workers/vision/image_input.py) -----------------------
    "IMAGE_BASE64_EMPTY": (
        {
            "en": "image_base64 is empty. Send the raw base64 of the image bytes, optionally prefixed with a data: URI header.",
            "pt": "image_base64 está vazio. Envie o base64 dos bytes da imagem, opcionalmente com o prefixo de um data: URI.",
        },
        ["fix_input"],
    ),
    "IMAGE_BASE64_NO_PAYLOAD": (
        {
            "en": "image_base64 contains a data: URI header but no base64 payload.",
            "pt": "image_base64 contém o cabeçalho de um data: URI, mas nenhum conteúdo base64.",
        },
        ["fix_input"],
    ),
    "IMAGE_BASE64_INVALID": (
        {
            "en": "image_base64 is not valid base64: {reason}. Send the raw base64 of the image bytes (a data: URI prefix is accepted).",
            "pt": "image_base64 não é base64 válido: {reason}. Envie o base64 dos bytes da imagem (um prefixo data: URI é aceito).",
        },
        ["fix_input"],
    ),
    "IMAGE_BASE64_ZERO_BYTES": (
        {
            "en": "image_base64 decoded to zero bytes.",
            "pt": "image_base64 decodificou para zero bytes.",
        },
        ["fix_input"],
    ),
    "IMAGE_TOO_LARGE": (
        {
            "en": "Image is {size_mb}MB, over the {max_size_mb}MB limit (VISION_MAX_IMAGE_SIZE_MB).",
            "pt": "A imagem tem {size_mb}MB, acima do limite de {max_size_mb}MB (VISION_MAX_IMAGE_SIZE_MB).",
        },
        ["fix_input"],
    ),
    "UNSUPPORTED_IMAGE_FORMAT": (
        {
            "en": "Unsupported image format. Accepted formats: {formats}.",
            "pt": "Formato de imagem não suportado. Formatos aceitos: {formats}.",
        },
        ["fix_input"],
    ),
}
