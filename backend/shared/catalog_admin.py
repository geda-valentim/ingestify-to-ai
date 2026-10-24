"""Bilingual texts of the admin / engine-administration / IAM-dependency refusals (P-13 slice 4).

``ADMIN_CATALOG[code] = ({"en": template, "pt": template}, next_steps)`` has the same
shape as ``error_catalog.CATALOG``, which merges it at import. English is written
natively; Portuguese translates it (these refusals used to be plain English or Portuguese
strings). ``{params}`` are named and must be identical in both languages.

Several refusals wrap a domain exception whose text carries the specifics ("limit_usd
must be positive"); that raw text stays in ``technical`` (English, as raised) while
``message`` is the localized sentence for the code.
"""

ADMIN_CATALOG = {
    # --- administrator / session gates ---------------------------------------------
    "ADMIN_REQUIRED": (
        {
            "en": "Access denied: administrator privileges are required.",
            "pt": "Acesso negado: privilégios de administrador necessários",
        },
        ["request_access"],
    ),
    "CURRENT_PASSWORD_REQUIRED": (
        {
            "en": "Confirm your current password (current_password) to do this.",
            "pt": "Confirme sua senha atual (current_password) para fazer isto.",
        },
        ["fix_input"],
    ),
    # --- /admin monitoring ---------------------------------------------------------
    "ADMIN_STATS_FAILED": (
        {"en": "The statistics could not be fetched.", "pt": "Não foi possível obter as estatísticas."},
        ["retry"],
    ),
    "STUCK_JOBS_LIST_FAILED": (
        {"en": "The stuck jobs could not be listed.", "pt": "Não foi possível listar os jobs travados."},
        ["retry"],
    ),
    "STUCK_JOBS_RECOVER_FAILED": (
        {"en": "The stuck jobs could not be recovered.", "pt": "Não foi possível recuperar os jobs travados."},
        ["retry"],
    ),
    "PAGES_RETRY_FAILED": (
        {"en": "The failed pages could not be retried.", "pt": "Não foi possível refazer as páginas com falha."},
        ["retry"],
    ),
    "CLEANUP_FAILED": (
        {"en": "The cleanup could not be completed.", "pt": "Não foi possível concluir a limpeza."},
        ["retry"],
    ),
    "HEALTH_CHECK_FAILED": (
        {"en": "The health check could not be completed.", "pt": "Não foi possível concluir a verificação de saúde."},
        ["retry"],
    ),
    "ADMIN_JOB_NOT_FOUND": (
        {"en": "Job {job_id} not found.", "pt": "Job {job_id} não encontrado."},
        [],
    ),
    "BROKER_MESSAGE_NOT_ORPHANED": (
        {
            "en": "The latest monitoring check did not flag this message as orphaned; wait for the next check.",
            "pt": "A última verificação do monitoramento não marcou esta mensagem como órfã; aguarde a próxima verificação.",
        },
        ["retry"],
    ),
    "BROKER_NO_WORKER_ANSWERED": (
        {
            "en": "No worker answered, so it cannot be confirmed that the task is not running.",
            "pt": "Nenhum worker respondeu; não é possível confirmar que a tarefa não está em execução.",
        },
        ["retry"],
    ),
    "BROKER_TASK_RUNNING": (
        {
            "en": "A worker is holding this task right now; it was not requeued.",
            "pt": "Um worker está com esta tarefa agora; ela não foi reenfileirada.",
        },
        [],
    ),
    "BROKER_MESSAGE_GONE": (
        {
            "en": "The message is no longer unacknowledged (it was acked or already restored).",
            "pt": "A mensagem não está mais sem confirmação (foi confirmada ou já restaurada).",
        },
        ["reload"],
    ),
    # --- engines (/admin/engines) ------------------------------------------------
    "ENGINE_NO_CREDENTIALS": (
        {"en": "The engine has no credentials.", "pt": "A engine não tem credenciais."},
        ["configure_credentials"],
    ),
    "ENGINE_SECRETS_KEY_MISSING": (
        {
            "en": "ENGINE_SECRETS_PUBLIC_KEY is not set on the server, so credentials cannot be stored.",
            "pt": "ENGINE_SECRETS_PUBLIC_KEY não está definida no servidor; as credenciais não podem ser guardadas.",
        },
        ["set_server_secret"],
    ),
    "REMOTE_WORKER_NOT_RUNNING": (
        {
            "en": "worker-remote is not running (docker compose --profile engines up -d worker-remote); "
            "only it can open credentials and read spend reports.",
            "pt": "O worker-remote não está em execução (docker compose --profile engines up -d worker-remote); "
            "só ele abre as credenciais e lê os relatórios de gasto.",
        },
        ["retry"],
    ),
    "REMOTE_WORKER_TIMEOUT": (
        {
            "en": "worker-remote did not answer within {seconds} s.",
            "pt": "O worker-remote não respondeu em {seconds} s.",
        },
        ["retry"],
    ),
    "LOCAL_ENGINE_NO_SPEND": (
        {
            "en": "The local engine has no provider spend.",
            "pt": "A engine local não tem gasto de provedor.",
        },
        [],
    ),
    "CAPACITY_EXCEEDED": (
        {
            "en": "The requested capacity does not fit the available GPU memory (VRAM).",
            "pt": "A capacidade pedida não cabe na memória de GPU (VRAM) disponível.",
        },
        ["fix_input"],
    ),
    "REMOTE_CAPACITY_EXCEEDED": (
        {
            "en": "The requested capacity exceeds what worker-remote can hold.",
            "pt": "A capacidade pedida excede o que o worker-remote comporta.",
        },
        ["fix_input"],
    ),
    "ENGINE_NOT_ACTIVATABLE": (
        {
            "en": "The engine cannot be activated yet; resolve the listed problems first.",
            "pt": "A engine ainda não pode ser ativada; resolva antes os problemas listados.",
        },
        ["fix_input"],
    ),
    "INVALID_BUDGET": (
        {
            "en": "The budget settings are not valid.",
            "pt": "As configurações de orçamento não são válidas.",
        },
        ["fix_input"],
    ),
    "INVALID_CREDENTIAL_FIELDS": (
        {
            "en": "The credential fields are not valid for this engine.",
            "pt": "Os campos de credencial não são válidos para esta engine.",
        },
        ["fix_input"],
    ),
    "CREDENTIALS_NOT_SUPPORTED": (
        {
            "en": "This type of engine takes no credentials.",
            "pt": "Este tipo de engine não usa credenciais.",
        },
        [],
    ),
    "ENGINE_STATE_CONFLICT": (
        {
            "en": "The engine's current state does not allow this change.",
            "pt": "O estado atual da engine não permite esta alteração.",
        },
        ["reload"],
    ),
    # --- routing (/admin/routing) ------------------------------------------------
    "ROUTE_REJECTED": (
        {
            "en": "The route cannot be saved with this configuration.",
            "pt": "A rota não pode ser salva com esta configuração.",
        },
        ["fix_input"],
    ),
    "ROUTE_NOT_FOUND": (
        {"en": "No route exists for this feature.", "pt": "Não há rota para esta funcionalidade."},
        [],
    ),
    # --- engine host agent -----------------------------------------------------------
    "HOST_OPERATION_MISMATCH": (
        {
            "en": "This operation belongs to another host.",
            "pt": "Esta operação pertence a outro host.",
        },
        ["register_host"],
    ),
}
