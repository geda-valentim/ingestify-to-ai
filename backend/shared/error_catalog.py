"""One Portuguese message catalog for engine-control, execution-profile, access,
IAM and root error codes (spec 0009 CA1: never show only a code).

Every refusal keeps its machine ``code`` unchanged. ``detail()`` adds:

- ``message``: what happened, in plain Portuguese;
- ``next_steps``: identifiers from the closed vocabulary below, which the admin
  UI turns into labels and buttons;
- ``cause``: the inner gate when a generic code wraps one
  (``INVALID_CONFIGURATION`` → ``HOST_AGENT_NOT_READY``); ``message`` and
  ``next_steps`` then describe the cause;
- ``technical``: the original text when it carries more than the code (it never
  holds secrets: callers already redact what they raise).

``tests/test_error_catalog.py`` scans the source of these modules and fails
when a code is raised without an entry here.
"""

import re
from datetime import datetime

# Closed vocabulary of next steps (labels live in frontend/lib/admin-errors.ts).
NEXT_STEPS = {
    "test_connection",  # run "Testar" on the engine (records the provider identity)
    "configure_credentials",  # save provider credentials on the engine
    "bind_profile",  # choose a published execution profile and bind it
    "create_profile",  # create (and publish) an execution profile
    "publish_revision",  # publish a revision of the execution profile
    "classify_environment",  # classify the engine environment (Admin → Acesso)
    "redeploy",  # run Deploy / Aplicar perfil
    "reload",  # re-read the current state before retrying
    "retry",  # try again later
    "wait_operation",  # wait for / cancel the running operation
    "recover_operation",  # review the operation and use Recover
    "check_host",  # check the local host agent service
    "register_host",  # re-register the host (scripts/register_engine_host.py)
    "check_watchdog",  # restore the cleanup watchdog
    "set_budget",  # reserve a positive US$ cap / raise the budget
    "set_warm_until",  # choose how long to keep the pool warm
    "request_access",  # ask an administrator for access
    "fix_input",  # correct the submitted field(s)
    "enable_control",  # turn on ENGINE_CONTROL_ENABLED / the access schema
    "set_root_token",  # set ROOT_SETUP_TOKEN on the server
}

PROFILE_ACTIONS_EXEMPT = ("test", "reconcile")

_HOST_AGENT_HINT = (
    "Verifique o serviço ingestify-engine-host-agent no servidor "
    "(journalctl -u ingestify-engine-host-agent)."
)

# code -> (message template, next steps). Templates may use {for_feature},
# {host} and {since}; missing context renders as an empty string.
CATALOG = {
    # --- setup / configuration -------------------------------------------------
    "RUNTIME_PROFILE_REQUIRED": (
        "Esta engine ainda não tem perfil de execução vinculado{for_feature}. "
        "Vincule um perfil publicado em Admin → Perfis de execução (ou crie um) antes de operar.",
        ["bind_profile", "create_profile"],
    ),
    "NOTHING_TO_COOL_DOWN": (
        "Nada para liberar{for_feature}: sem perfil de execução vinculado, o plano de "
        "controle nunca aqueceu containers nesta engine, e o deploy padrão já escala para "
        "zero sozinho quando fica ocioso.",
        [],
    ),
    "RUNTIME_PROFILE_NOT_FOUND": (
        "Não há perfil de execução desejado{for_feature} nesta engine (ou ele não está no seu escopo).",
        ["bind_profile"],
    ),
    "RUNTIME_OPERATION_REQUIRED": (
        "Esta engine é gerenciada pelo plano de controle: mudanças de runtime passam por um "
        "perfil de execução e uma operação revisada, não pela edição direta.",
        ["bind_profile"],
    ),
    "TEST_CONNECTION_FIRST": (
        "A conexão com o provedor ainda não foi verificada. Use “Testar conexão” nesta engine; "
        "depois vincule um perfil de execução.",
        ["test_connection", "bind_profile"],
    ),
    "CREDENTIALS_REQUIRED": (
        "Salve as credenciais do provedor nesta engine (aba Configuração) e depois teste a conexão.",
        ["configure_credentials", "test_connection"],
    ),
    "CREDENTIALS_NOT_ALLOWED_IN_PROFILE": (
        "Perfis de execução não guardam credenciais. Remova-as do perfil; credenciais ficam na engine.",
        ["fix_input"],
    ),
    "CLEANUP_CREDENTIAL_REQUIRED": (
        "Há containers pagos que ainda precisam ser liberados. Execute “Liberar modelo” e confirme "
        "a liberação antes de trocar ou remover as credenciais.",
        ["wait_operation"],
    ),
    "CONTROL_NOT_ENABLED": (
        "O plano de controle de engines está desligado nesta instalação (ENGINE_CONTROL_ENABLED).",
        ["enable_control"],
    ),
    "ACCESS_NOT_ENABLED": (
        "Perfis de execução e escopos de acesso estão desligados nesta instalação "
        "(IAM_MODE diferente de enforce).",
        ["enable_control"],
    ),
    "ACCESS_SCHEMA_NOT_READY": (
        "As tabelas de acesso ainda não foram migradas. Rode as migrações do backend e tente de novo.",
        ["enable_control", "retry"],
    ),
    "ENGINE_ENVIRONMENT_REQUIRED": (
        "Classifique o ambiente desta engine em Admin → Acesso antes de vincular um perfil.",
        ["classify_environment"],
    ),
    "CONSUMER_NOT_CLASSIFIED": (
        "Um consumidor dos recursos desta engine ainda não tem ambiente classificado. "
        "Classifique-o em Admin → Acesso.",
        ["classify_environment"],
    ),
    "FEATURE_NOT_SUPPORTED": (
        "Este adaptador não oferece esta feature.",
        ["fix_input"],
    ),
    "FEATURE_UNSUPPORTED": (
        "Este adaptador não oferece esta feature.",
        ["fix_input"],
    ),
    "INVALID_PROVIDER_VALUE": (
        "Um valor específico do provedor é inválido para este adaptador.",
        ["fix_input"],
    ),
    "PROVIDER_FIELDS_REQUIRED": (
        "Preencha os campos do provedor exigidos por este adaptador.",
        ["fix_input"],
    ),
    "INVALID_CONFIGURATION": (
        "A configuração enviada foi recusada.",
        ["fix_input"],
    ),
    "INVALID_OPERATION": (
        "A operação não pode ser planejada com a configuração atual.",
        ["reload"],
    ),
    "SLUG_IN_USE": ("Já existe uma engine com este identificador. Escolha outro.", ["fix_input"]),
    "SYSTEM_ENGINE_ALREADY_EXISTS": (
        "Esta engine de sistema já existe e não pode ser criada de novo.",
        [],
    ),
    "ENGINE_NOT_FOUND": ("Engine não encontrada (ou fora do seu escopo).", ["reload"]),
    # --- local host agent ---------------------------------------------------------
    "HOST_AGENT_NOT_READY": (
        "O agente do host local{host} não responde (sem heartbeat recente){since}. " + _HOST_AGENT_HINT,
        ["check_host"],
    ),
    "HOST_IDENTITY_REQUIRED": (
        "O agente do host não apresentou uma identidade registrada. Registre o host de novo "
        "com scripts/register_engine_host.py.",
        ["register_host"],
    ),
    "INVALID_INVENTORY": (
        "O agente do host enviou um inventário inválido.",
        ["check_host"],
    ),
    "SERVICE_NOT_REGISTERED": (
        "O serviço desta feature não está registrado no host{host}. Registre o host de novo "
        "incluindo o serviço (--service).",
        ["register_host"],
    ),
    "GPU_UUID_NOT_REGISTERED": (
        "A GPU escolhida não está no inventário registrado do host{host}. Cadastre o UUID da GPU "
        "na engine e registre o host com --gpu-uuid.",
        ["register_host", "fix_input"],
    ),
    "GPU_NOT_REGISTERED": (
        "A GPU pedida não está registrada neste host. Registre o host com --gpu-uuid.",
        ["register_host"],
    ),
    "PROFILE_INVENTORY_CHANGED": (
        "O inventário do host mudou desde o vínculo (GPU ou manifests). Vincule o perfil de novo.",
        ["bind_profile"],
    ),
    "REGISTERED_MANIFEST_CHANGED": (
        "Os arquivos docker compose registrados mudaram, e o agente do host recusa operar. "
        "Registre o host de novo (scripts/register_engine_host.py).",
        ["register_host"],
    ),
    "MANIFEST_STALE": (
        "O plano foi feito com outra versão dos manifests do host. Revise e planeje de novo.",
        ["reload"],
    ),
    "ACTION_OR_TARGET_NOT_REGISTERED": (
        "O host não tem esta ação ou serviço registrados.",
        ["register_host"],
    ),
    "REGISTERED_COMMAND_NOT_SUPPORTED": (
        "O comando registrado do serviço não é suportado pelo agente do host.",
        ["register_host"],
    ),
    "IMAGE_MISMATCH": (
        "A imagem em execução difere da registrada. Registre o host de novo após atualizar as imagens.",
        ["register_host"],
    ),
    "HOST_AUTHORITY_UNAVAILABLE": (
        "O agente do host perdeu contato com a API durante a operação. " + _HOST_AGENT_HINT,
        ["check_host", "recover_operation"],
    ),
    "HOST_COMMAND_FAILED": (
        "Um comando docker compose falhou no host. Veja os eventos da operação e "
        "journalctl -u ingestify-engine-host-agent.",
        ["check_host", "recover_operation"],
    ),
    "HOST_COMMAND_TIMEOUT": (
        "Um comando docker compose demorou demais no host.",
        ["check_host", "recover_operation"],
    ),
    "HOST_EFFECT_UNCERTAIN": (
        "O agente do host reiniciou no meio de uma operação; o efeito é incerto. Revise e use Recuperar.",
        ["recover_operation"],
    ),
    "MODEL_READINESS_TIMEOUT": (
        "Os workers não confirmaram o modelo carregado a tempo.",
        ["check_host", "retry"],
    ),
    "LIVE_SINGLE_RESIDENT_REQUIRED": (
        "Transcrição ao vivo exige uma única réplica com uma execução por worker.",
        ["fix_input"],
    ),
    "LIVE_REQUIRES_CUDA": (
        "Transcrição ao vivo exige uma GPU (gpu_ref) no perfil.",
        ["fix_input"],
    ),
    "HOST_APPLY_FAILED": (
        "O agente do host não conseguiu aplicar a operação. Veja os eventos da operação e "
        "journalctl -u ingestify-engine-host-agent.",
        ["check_host", "recover_operation"],
    ),
    "TEST_FAILED": (
        "O teste de conexão com o provedor falhou. Confira as credenciais e tente de novo.",
        ["configure_credentials", "test_connection"],
    ),
    "CANCELLED": ("A operação foi cancelada.", []),
    # --- models / revisions / profiles -------------------------------------------
    "MODEL_PROFILE_UNAVAILABLE": (
        "O modelo escolhido não está disponível para este adaptador e feature.",
        ["fix_input"],
    ),
    "MODEL_FOOTPRINT_NOT_QUALIFIED": (
        "O modelo ainda não tem consumo de memória qualificado; não pode ser usado em operação.",
        ["fix_input"],
    ),
    "MODEL_METADATA_CHANGED": (
        "Os metadados do modelo mudaram desde a revisão do perfil. Crie e publique uma nova revisão compatível.",
        ["publish_revision"],
    ),
    "WHISPERX_CONTROL_PROFILE_NOT_QUALIFIED": (
        "Engines com manifest WhisperX ainda não podem ser operadas pelo plano de controle.",
        [],
    ),
    "PUBLISHED_REVISION_REQUIRED": (
        "Escolha uma revisão publicada (e não arquivada) do perfil de execução.",
        ["publish_revision", "bind_profile"],
    ),
    "PROFILE_INCOMPATIBLE": (
        "O perfil escolhido não é compatível com esta engine (adaptador, feature ou ambiente). "
        "Escolha outro ou crie um compatível.",
        ["bind_profile", "create_profile"],
    ),
    "PROFILE_CONTENT_MISMATCH": (
        "O conteúdo enviado difere da revisão publicada. Recarregue e vincule de novo.",
        ["reload"],
    ),
    "PROFILE_NOT_FOUND": ("Perfil de execução não encontrado (ou fora do seu escopo).", ["reload"]),
    "SOURCE_PROFILE_NOT_FOUND": (
        "O perfil de origem deste vínculo não existe mais ou saiu do seu escopo.",
        ["bind_profile"],
    ),
    "PROFILE_ARCHIVED": ("Este perfil está arquivado e não aceita novos vínculos nem revisões.", ["bind_profile"]),
    "REVISION_NOT_FOUND": ("Revisão do perfil não encontrada.", ["reload"]),
    "REVISION_NOT_PUBLISHABLE": (
        "Esta revisão não pode ser publicada (já publicada ou incompleta).",
        ["reload"],
    ),
    "POLICY_NOT_FOUND": ("Política de acesso não encontrada.", ["reload"]),
    "USE_WARM_DURATION": (
        "Perfis publicados usam duração de aquecimento (warm_for_seconds), não um horário fixo.",
        ["fix_input"],
    ),
    "WARM_DURATION_REQUIRED": ("Informe por quanto tempo manter aquecido.", ["set_warm_until"]),
    "WARM_EXPIRATION_REQUIRED": (
        "Defina até quando manter aquecido (ou vincule um perfil com prazo de aquecimento) antes de "
        "iniciar ou aquecer.",
        ["set_warm_until", "bind_profile"],
    ),
    "INVALID_WARM_DEADLINE": (
        "O prazo de aquecimento é inválido (no passado ou além do permitido pelo perfil).",
        ["set_warm_until"],
    ),
    "WARM_DEADLINE": ("O prazo de aquecimento terminou durante a operação.", ["set_warm_until"]),
    # --- operations ----------------------------------------------------------------
    "ACTION_UNSUPPORTED": ("Este adaptador não oferece esta operação.", []),
    "VERSION_CONFLICT": (
        "Os dados mudaram desde que a página foi carregada. Recarregue e revise antes de repetir.",
        ["reload"],
    ),
    "OPERATION_CONFLICT": (
        "Já existe uma operação em andamento nesta engine. Aguarde ou cancele-a.",
        ["wait_operation"],
    ),
    "RESOURCE_LOCKED": (
        "Um recurso desta engine está preso a uma operação ativa ou incerta.",
        ["wait_operation", "recover_operation"],
    ),
    "RESOURCE_OWNED_BY_ANOTHER_ENGINE": (
        "O recurso deste perfil já pertence a outra engine.",
        ["bind_profile"],
    ),
    "RESOURCE_OWNERSHIP_CONFLICT": (
        "Outra engine reivindicou o mesmo recurso ao mesmo tempo. Recarregue.",
        ["reload"],
    ),
    "RESOURCE_NOT_FOUND": ("Recurso não encontrado.", ["reload"]),
    "PLAN_NOT_FOUND": ("O plano não existe ou expirou. Revise a operação de novo.", ["reload"]),
    "PLAN_STALE": (
        "O plano ficou desatualizado (engine, perfil ou credenciais mudaram). Revise de novo.",
        ["reload"],
    ),
    "OPERATION_NOT_FOUND": ("Operação não encontrada (ou fora do seu escopo).", ["reload"]),
    "IDEMPOTENCY_KEY_REQUIRED": ("A requisição precisa de uma chave de idempotência.", ["retry"]),
    "IDEMPOTENCY_CONFLICT": (
        "Esta chave de idempotência já foi usada com outro plano. Revise a operação de novo.",
        ["reload"],
    ),
    "PAID_CONFIRMATION_REQUIRED": (
        "Esta operação pode gerar custo: confirme a operação paga para continuar.",
        [],
    ),
    "PAID_BUDGET_REQUIRED": (
        "Esta operação pode gerar custo: informe um teto reservado maior que US$ 0.",
        ["set_budget"],
    ),
    "BUDGET_INSUFFICIENT": (
        "O orçamento restante da engine não cobre o teto reservado desta operação.",
        ["set_budget"],
    ),
    "BUDGET_STOP_UNCONFIRMED": (
        "Não foi possível confirmar que os containers pagos pararam. Verifique no provedor.",
        ["recover_operation"],
    ),
    "CONTROL_REDEPLOY_REQUIRED": (
        "O deploy atual não tem o protocolo de controle. Faça “Deploy” ou “Aplicar perfil” antes de "
        "escalar, aquecer ou liberar.",
        ["redeploy"],
    ),
    "HASHED_MODEL_LOCK_REQUIRED": (
        "O lock de modelos desta instalação não tem hashes; o deploy não pode ser reproduzido com segurança.",
        [],
    ),
    "CLEANUP_WATCHDOG_NOT_READY": (
        "O watchdog de limpeza do plano de controle não está ativo; operações que podem gerar custo "
        "ficam bloqueadas até ele voltar.",
        ["check_watchdog"],
    ),
    "SDK_AUTOSCALER_UNAVAILABLE": (
        "O SDK do provedor não expõe o autoscaler. Atualize o SDK e faça deploy de novo.",
        ["redeploy"],
    ),
    "POOL_OBSERVATION_UNAVAILABLE": (
        "O provedor não informou quantos containers estão vivos.",
        ["retry"],
    ),
    "WARM_POOL_NOT_VERIFIED": (
        "Os containers aquecidos não confirmaram o modelo carregado.",
        ["recover_operation"],
    ),
    "COOLDOWN_NOT_VERIFIED": (
        "Os containers não foram liberados no prazo observado. Verifique no provedor.",
        ["recover_operation"],
    ),
    "DEPLOYMENT_STOP_FAILED": ("O provedor recusou parar o deploy.", ["recover_operation"]),
    "DEPLOYMENT_STOP_NOT_VERIFIED": (
        "O deploy continua ativo após o pedido de parada.",
        ["recover_operation"],
    ),
    "DRAIN_TIMEOUT": ("O drain não terminou no prazo; trabalhos ainda estavam em andamento.", ["retry"]),
    "OPERATION_DEADLINE": ("A operação passou do prazo.", ["recover_operation"]),
    "PROCESS_DEADLINE": ("Um comando da operação passou do prazo.", ["recover_operation"]),
    "OPERATION_ABORTED": ("A operação foi interrompida.", ["recover_operation"]),
    "LEASE_LOST": ("O executor perdeu a posse da operação.", ["recover_operation"]),
    "EXECUTOR_LOST": ("O executor da operação parou de responder.", ["recover_operation"]),
    "EXECUTOR_NOT_NEUTRALIZED": (
        "O executor anterior ainda pode estar ativo; a recuperação precisa esperar.",
        ["wait_operation"],
    ),
    "RECOVERY_NOT_REQUIRED": ("Esta operação não precisa de recuperação.", []),
    "RECOVERY_STATE_UNCONFIRMED": (
        "Não foi possível confirmar o estado real para recuperar a operação.",
        ["recover_operation"],
    ),
    "EFFECT_ALREADY_ADMITTED": ("Este efeito já foi admitido para esta operação.", ["reload"]),
    "ADMISSION_AUTHORITY_UNAVAILABLE": (
        "Não foi possível verificar a autorização do efeito agora. Tente de novo.",
        ["retry"],
    ),
    "CLI_ADMISSION_LOST": ("A autorização do comando de linha foi perdida.", ["retry"]),
    "ENGINE_MAINTENANCE": ("A engine está em manutenção por uma operação em andamento.", ["wait_operation"]),
    "ENGINE_NOT_RUNNING": ("A engine não está em execução.", []),
    "INSTALLATION_PRINCIPAL_REQUIRED": (
        "Esta ação exige um usuário da instalação (não uma chave de API).",
        ["request_access"],
    ),
    "LEGACY_CONTEXT_INVALID": ("O contexto da requisição legada é inválido.", ["reload"]),
    # --- access / IAM ----------------------------------------------------------------
    "ACCESS_DENIED": ("Seu acesso não permite esta ação aqui.", ["request_access"]),
    "ACCESS_REVOKED": ("Seu acesso foi revogado durante a operação.", ["request_access"]),
    "LOGIN_SESSION_REQUIRED": ("Esta ação exige uma sessão de login (não uma chave de API).", []),
    "DELEGATION_EXCEEDED": (
        "Você não pode conceder mais do que a sua própria delegação permite.",
        ["request_access"],
    ),
    "DELEGATION_INVALID": ("A delegação informada é inválida.", ["fix_input"]),
    "SELF_GRANT": ("Ninguém pode conceder papéis a si mesmo.", ["request_access"]),
    "ROLE_ABOVE_GRANTOR": ("Você não pode conceder um papel acima do seu.", ["request_access"]),
    "ROLE_UNKNOWN": ("Papel desconhecido.", ["fix_input"]),
    "UNKNOWN_ROLE": ("Papel desconhecido.", ["fix_input"]),
    "PERMISSIONS_OUTSIDE_ROLE": ("Há permissões fora do que o papel permite.", ["fix_input"]),
    "FIELD_NOT_ALLOWED_FOR_ROLE": ("Um campo enviado não se aplica a este papel.", ["fix_input"]),
    "BINDING_EXISTS": ("Este usuário já tem este papel.", ["reload"]),
    "BINDING_NOT_FOUND": ("Concessão não encontrada.", ["reload"]),
    "GRANT_NOT_FOUND": ("Concessão não encontrada.", ["reload"]),
    "PROJECT_NOT_FOUND": ("Projeto não encontrado (ou fora do seu acesso).", ["reload"]),
    "FOLDER_NOT_FOUND": ("Pasta não encontrada (ou fora do seu acesso).", ["reload"]),
    "ALREADY_REVOKED": ("Esta concessão já foi revogada.", ["reload"]),
    "GRANT_EXPIRY_INVALID": ("A validade da concessão é inválida.", ["fix_input"]),
    "INVALID_EXPIRES_AT": ("A data de expiração é inválida (use data e hora ISO-8601 no futuro).", ["fix_input"]),
    "GRANT_TARGET_NOT_FOUND": ("O alvo da concessão não existe.", ["fix_input"]),
    "INVALID_SUBJECT": ("O usuário ou chave informado é inválido.", ["fix_input"]),
    "SUBJECT_NOT_FOUND": ("Usuário não encontrado.", ["reload"]),
    "PRINCIPAL_EXISTS": ("Este principal já existe.", ["reload"]),
    "PRINCIPAL_NOT_FOUND": ("Principal não encontrado.", ["reload"]),
    "TOO_MANY_CHECKS": ("Verificações demais em uma só requisição.", ["fix_input"]),
    "UNSUPPORTED_PERMISSION": ("Permissão desconhecida.", ["fix_input"]),
    # --- root (spec 0019) ---------------------------------------------------------------
    "ROOT_SETUP_TOKEN_REQUIRED": (
        "Esta instalação ainda não tem usuário root. Defina ROOT_SETUP_TOKEN no servidor para criá-lo.",
        ["set_root_token"],
    ),
    "ROOT_SETUP_TOKEN_INVALID": ("Token de configuração ausente ou inválido.", ["fix_input"]),
    "ROOT_IMMUTABLE": ("O usuário root não pode ser desativado nem perder o acesso de administrador.", []),
    # --- default execution profiles at installation (spec 0020 seed report) ----
    "BOOTSTRAP_ACTOR_REQUIRED": (
        "Somente o root (ou outro admin de bootstrap ativo) pode semear os perfis de execução padrão.",
        ["request_access"],
    ),
    "MODEL_NOT_APPROVED": (
        "Este modelo não está aprovado no catálogo com a configuração atual da instalação; "
        "nenhum perfil padrão é criado para ele.",
        [],
    ),
    "ADAPTER_NOT_REGISTERED": (
        "O adapter deste modelo não está registrado nesta instalação.",
        [],
    ),
    "NO_REGISTERED_HOST": (
        "Nenhum agente de host registrado: perfis locais precisam do host. Eles são criados e "
        "vinculados no primeiro heartbeat do agente.",
        ["register_host"],
    ),
    "PROVIDER_SETTINGS_REQUIRED": (
        "O adapter exige parâmetros de provedor que a configuração atual não define.",
        ["create_profile"],
    ),
    "BOUND_TO_LIBRARY_PROFILE": (
        "A engine já usa um perfil da biblioteca nesta feature; o perfil padrão não é vinculado por cima.",
        [],
    ),
    "RUNTIME_PROFILE_EXISTS": (
        "A engine já tem perfil desejado{for_feature}; o vínculo automático não o substitui.",
        [],
    ),
    "INVALID_SETTINGS": (
        "A configuração atual da engine não forma um RuntimeSettings válido; revise o binding da feature.",
        ["create_profile"],
    ),
    "SEEDED_PROFILE_STALE": (
        "A configuração da engine mudou desde que o perfil padrão foi criado, e o perfil já foi "
        "alterado por um administrador; o vínculo automático não o sobrescreve. Revise e publique "
        "uma revisão do perfil com a configuração atual e vincule-o à engine.",
        ["publish_revision", "bind_profile"],
    ),
    "HOST_AMBIGUOUS": (
        "Mais de um host registrado atende a esta feature (e GPU); o perfil padrão local precisa "
        "de um host concreto. Crie o perfil escolhendo o host.",
        ["create_profile"],
    ),
    "ENVIRONMENT_UNKNOWN": (
        "ENVIRONMENT do servidor não é um ambiente conhecido (development/dev/local, staging, "
        "production/prod); nenhum perfil padrão é criado nem engine classificada. Ajuste "
        "ENVIRONMENT ou classifique as engines em Admin → Acesso.",
        ["classify_environment"],
    ),
}

_CODE = re.compile(r"^([A-Z][A-Z0-9_]{3,})(?:\s*:\s*(.*))?$", re.S)


class Gate(ValueError):
    """An adapter gate with context for the message; ``str()`` stays the bare code."""

    def __init__(self, code, **context):
        super().__init__(code)
        self.code = code
        self.context = context


def split(text):
    """``"CODE"`` / ``"CODE: detail"`` → ``(CODE, detail)``; anything else → ``(None, text)``."""
    match = _CODE.match(str(text or "").strip())
    if not match:
        return None, text
    return match.group(1), (match.group(2) or None)


class _Blank(dict):
    def __missing__(self, key):
        return ""


def _since(seen_at):
    if not seen_at:
        return " (nenhum heartbeat registrado)"
    minutes = int((datetime.utcnow() - seen_at).total_seconds() // 60)
    if minutes < 1:
        return " há menos de 1 minuto"
    if minutes < 120:
        return f" há {minutes} minuto{'s' if minutes != 1 else ''}"
    return f" há {minutes // 60} horas"


def describe(code, *, feature=None, needs_connection=False, **context):
    """``(message, next_steps)`` for a known code, else ``(None, [])``."""
    known = CATALOG.get(code)
    if not known:
        return None, []
    template, steps = known
    values = _Blank(
        for_feature=f" para {feature}" if feature else "",
        host=f" “{context['host']}”" if context.get("host") else "",
        since=_since(context.get("seen_at")) if "seen_at" in context else "",
    )
    message = template.format_map(values)
    steps = list(steps)
    if needs_connection and code in ("RUNTIME_PROFILE_REQUIRED", "NOTHING_TO_COOL_DOWN"):
        message += " A conexão com o provedor ainda não foi verificada: use “Testar” primeiro."
        steps = ["test_connection"] + [s for s in steps if s != "test_connection"]
        if code == "NOTHING_TO_COOL_DOWN":
            steps.append("bind_profile")
    return message, steps


def detail(code, *, text=None, cause=None, context=None, feature=None, needs_connection=False):
    """The HTTP ``detail`` body: ``code`` unchanged plus human guidance.

    ``text`` is the raw exception text; a ``"CODE: rest"`` text whose CODE differs
    from ``code`` is treated as the cause when ``cause`` is not given.
    """
    context = dict(context or {})
    raw_code, rest = split(text) if text else (None, None)
    if cause is None and raw_code and raw_code != code:
        cause = raw_code
    out = {"code": code}
    message, steps = describe(
        cause or code, feature=feature, needs_connection=needs_connection, **context
    )
    if message is None and cause:
        message, steps = describe(code, feature=feature)
    if message is None:
        message = text if text and not raw_code else None
    out["message"] = message or code
    if cause:
        out["cause"] = cause
    out["next_steps"] = steps
    technical = rest if raw_code else text
    if technical and technical != out["message"]:
        out["technical"] = str(technical)[:500]
    return out


def enrich(value):
    """Add guidance to an HTTP ``detail`` that carries a ``code`` but none yet.

    Details that already have ``next_steps`` (built by ``detail()``) and details
    without a code (plain strings, validation lists) are returned unchanged; extra
    keys are kept.
    """
    if not isinstance(value, dict) or not isinstance(value.get("code"), str):
        return value
    if "next_steps" in value:
        return value
    code = value["code"]
    text = value.get("message")
    cause = value.get("cause")
    if code not in CATALOG and not (cause in CATALOG or split(text)[0] in CATALOG):
        return value
    guided = detail(code, text=None if text == code else text, cause=cause)
    return {**value, **guided}


def operation_error(error):
    """An operation's stored ``error`` plus ``human_message``/``next_steps`` for its code.

    The stored ``code``/``message`` (technical, e.g. ``HOST_COMMAND_FAILED:1``) stay as
    they are; unknown codes are returned unchanged.
    """
    if not isinstance(error, dict):
        return error
    code = split(error.get("code"))[0]
    message, steps = describe(code) if code else (None, [])
    if not message:
        return error
    return {**error, "human_message": message, "next_steps": steps}


def needs_connection(engine, descriptor):
    """True when the adapter binds profiles only after a verified provider identity."""
    return bool(descriptor.get("requires_control_identity")) and not (
        engine.config or {}
    ).get("control_identity")


def host_context(host_id, host):
    """Context for HOST_AGENT_NOT_READY from a ControlHost row (or None)."""
    return {"host": host_id, "seen_at": getattr(host, "seen_at", None)}
