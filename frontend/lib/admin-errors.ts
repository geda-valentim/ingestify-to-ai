import { ApiError } from "@/lib/api";

/**
 * Admin errors follow `backend/shared/error_catalog.py` (spec 0009 CA1): the API keeps
 * a stable `code` and adds a Portuguese `message`, `next_steps` (closed vocabulary
 * below), an optional inner `cause` and a `technical` detail. The UI shows the
 * message and next steps first and the code only as a small reference for support.
 *
 * Every next step of the backend vocabulary needs a label here
 * (`tests/test_error_catalog.py` checks it).
 */
export const NEXT_STEP_LABELS: Record<string, string> = {
  test_connection: "Testar conexão",
  configure_credentials: "Configurar credenciais",
  bind_profile: "Escolher perfil de execução",
  create_profile: "Criar perfil de execução",
  publish_revision: "Publicar uma revisão do perfil",
  classify_environment: "Classificar o ambiente da engine",
  redeploy: "Fazer deploy / aplicar perfil",
  reload: "Recarregar e revisar",
  retry: "Tentar de novo mais tarde",
  wait_operation: "Aguardar ou cancelar a operação em andamento",
  recover_operation: "Revisar a operação e reconciliar",
  check_host: "Verificar o agente do host (journalctl -u ingestify-engine-host-agent)",
  register_host: "Registrar o host de novo (scripts/register_engine_host.py)",
  check_watchdog: "Verificar o watchdog do plano de controle",
  set_budget: "Ajustar o teto reservado / orçamento",
  set_warm_until: "Definir até quando manter aquecido",
  request_access: "Pedir acesso a um administrador",
  fix_input: "Corrigir os campos enviados",
  enable_control: "Habilitar o controle na instalação",
  set_root_token: "Definir ROOT_SETUP_TOKEN no servidor",
};

export interface GuidedError {
  message: string;
  nextSteps: string[];
  code?: string;
  cause?: string;
  technical?: string;
  status?: number;
}

const isCode = (value: unknown): value is string =>
  typeof value === "string" && /^[A-Z][A-Z0-9_]{3,}$/.test(value);

/** Normalise anything thrown by the admin API clients into message + next steps. */
export function guidedError(error: unknown, fallback = "Falha na operação"): GuidedError {
  if (error == null) return { message: fallback, nextSteps: [] };
  const status = error instanceof ApiError ? error.status : undefined;
  const data =
    error instanceof ApiError
      ? (error.response.data as { detail?: unknown } | null)
      : null;
  const detail = data?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    const code = typeof d.code === "string" ? d.code : undefined;
    const message =
      typeof d.message === "string" && d.message && d.message !== code
        ? d.message
        : fallback;
    return {
      message,
      code,
      status,
      cause: typeof d.cause === "string" ? d.cause : undefined,
      technical: typeof d.technical === "string" ? d.technical : undefined,
      nextSteps: Array.isArray(d.next_steps)
        ? d.next_steps.filter((s): s is string => typeof s === "string")
        : [],
    };
  }
  if (Array.isArray(detail)) {
    const fields = detail
      .map((e: { loc?: unknown[]; msg?: string }) =>
        `${(e.loc || []).slice(1).join(".") || "campo"}: ${e.msg ?? ""}`,
      )
      .join("; ");
    return {
      message: "Alguns campos são inválidos.",
      technical: fields,
      nextSteps: ["fix_input"],
      status,
    };
  }
  if (typeof detail === "string")
    return isCode(detail)
      ? { message: fallback, code: detail, nextSteps: [], status }
      : { message: detail, nextSteps: [], status };
  const text = error instanceof Error ? error.message : String(error);
  return isCode(text)
    ? { message: fallback, code: text, nextSteps: [], status }
    : { message: text || fallback, nextSteps: [], status };
}

/** An operation's stored error (`human_message`/`next_steps` added by the API). */
export function guidedOperationError(error: {
  code?: string;
  message?: string;
  human_message?: string;
  next_steps?: string[];
} | null): GuidedError | null {
  if (!error) return null;
  const technical =
    error.message && error.message !== error.code ? error.message : undefined;
  return {
    message: error.human_message || technical || "A operação falhou.",
    code: error.code,
    technical: error.human_message ? technical : undefined,
    nextSteps: error.next_steps || [],
  };
}
