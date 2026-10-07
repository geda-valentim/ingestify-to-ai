import schemaDocument from "../../docs/doc2md_openapi.json";
import { DOCS_API_URL } from "./config";
import type { DocsLang } from "./topics";

type Schema = {
  $ref?: string; type?: string; format?: string; description?: string;
  anyOf?: Schema[]; oneOf?: Schema[]; items?: Schema;
  properties?: Record<string, Schema>; required?: string[];
  [key: string]: unknown;
};
type Content = Record<string, { schema?: Schema }>;
type Operation = {
  operationId: string; summary?: string; description?: string; tags?: string[];
  "x-access": string; "x-contract-notes"?: string[];
  parameters?: { name: string; in: string; required?: boolean; description?: string; schema?: Schema }[];
  requestBody?: { required?: boolean; content: Content };
  responses: Record<string, { description?: string; content?: Content }>;
};
const spec = schemaDocument as unknown as {
  paths: Record<string, Record<string, Operation>>;
  components: { schemas: Record<string, Schema> };
  "x-websockets": { path: string; authentication: string; protocol: string }[];
};
const METHODS = new Set(["get", "post", "put", "patch", "delete", "options", "head", "trace"]);

function Type({ schema = {} }: { schema?: Schema }): React.ReactNode {
  if (schema.$ref) {
    const name = schema.$ref.split("/").at(-1)!;
    return <a href={"#model-" + name} className="text-primary underline break-all">{name}</a>;
  }
  const alternatives = schema.anyOf ?? schema.oneOf;
  if (alternatives) return <>{alternatives.map((item, index) => <span key={index}>{index > 0 && " / "}<Type schema={item} /></span>)}</>;
  if (schema.type === "array") return <>array&lt;<Type schema={schema.items} />&gt;</>;
  return <>{schema.type ?? "object"}{schema.format && ` (${schema.format})`}</>;
}

function limits(schema: Schema) {
  return ["default", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "pattern", "additionalProperties"]
    .filter((key) => key in schema).map((key) => `${key}=${JSON.stringify(schema[key])}`).join("; ");
}

function resolve(schema: Schema): Schema {
  return schema.$ref ? spec.components.schemas[schema.$ref.split("/").at(-1)!] : schema;
}

function Grid({ columns, rows }: { columns: string[]; rows: React.ReactNode[][] }) {
  return <div className="overflow-x-auto rounded-md border"><table className="w-full text-sm"><thead className="bg-muted/50"><tr>
    {columns.map((column) => <th key={column} className="px-3 py-2 text-left font-medium">{column}</th>)}
  </tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-t align-top">
    {row.map((cell, i) => <td key={i} className="px-3 py-2 break-words [overflow-wrap:anywhere]">{cell}</td>)}
  </tr>)}</tbody></table></div>;
}

function Fields({ schema, pt }: { schema: Schema; pt: boolean }) {
  const model = resolve(schema);
  if (!model.properties) return null;
  return <Grid columns={pt ? ["Campo", "Obrigatório", "Tipo", "Padrões/limites", "Descrição"] : ["Field", "Required", "Type", "Defaults/limits", "Description"]}
    rows={Object.entries(model.properties).map(([key, field]) => [<code key={key}>{key}</code>,
      model.required?.includes(key) ? (pt ? "sim" : "yes") : (pt ? "não" : "no"),
      <Type key="type" schema={field} />, limits(field), field.description])} />;
}

export function ApiReference({ lang }: { lang: DocsLang }) {
  const pt = lang === "pt";
  const access: Record<string, string> = pt ? {
    public: "Público", user: "JWT ou API key", jwt: "JWT", admin: "Administrador: JWT ou API key",
    "admin-session": "Administrador: somente JWT, sem X-API-Key", "engine-host": "X-Engine-Host-Token do host",
  } : {
    public: "Public", user: "JWT or API key", jwt: "JWT", admin: "Admin: JWT or API key",
    "admin-session": "Admin: JWT session only, without X-API-Key", "engine-host": "Host X-Engine-Host-Token",
  };
  const entries = Object.entries(spec.paths).flatMap(([path, item]) => Object.entries(item)
    .filter(([method]) => METHODS.has(method)).map(([method, operation]) => ({ path, method, operation })));
  const groups = Array.from(new Set(entries.map(({ operation }) => operation.tags?.[0] ?? "General")));
  return <section id="api-reference" className="space-y-6 scroll-mt-24">
    <h1 className="text-3xl font-semibold tracking-tight">{pt ? "Referência completa da API" : "Complete API reference"}</h1>
    <p className="text-muted-foreground">{pt
      ? `${entries.length} operações HTTP, ${(spec["x-websockets"] ?? []).length} WebSocket e ${Object.keys(spec.components.schemas).length} modelos. Parâmetros, corpos, limites e respostas vêm do OpenAPI da aplicação. As descrições do backend são mantidas no idioma original.`
      : `${entries.length} HTTP operations, ${(spec["x-websockets"] ?? []).length} WebSocket and ${Object.keys(spec.components.schemas).length} models. Parameters, bodies, constraints and responses come from the application OpenAPI. Backend descriptions are retained in their original language.`}</p>
    <p>{pt ? "Base da API:" : "API base:"} <code className="break-all">{DOCS_API_URL}</code>. <a className="text-primary underline" href={`${DOCS_API_URL}/openapi.json`}>OpenAPI JSON</a> · <a className="text-primary underline" href={`${DOCS_API_URL}/docs`}>Swagger</a></p>
    <nav aria-label={pt ? "Grupos de endpoints" : "Endpoint groups"} className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
      {groups.map((tag) => <a key={tag} className="text-primary underline" href={"#group-" + tag.toLowerCase().replace(/[^a-z0-9]+/g, "-")}>{tag}</a>)}
      <a className="text-primary underline" href="#websockets">WebSocket</a><a className="text-primary underline" href="#models">{pt ? "Modelos" : "Models"}</a>
    </nav>
    <div className="space-y-2 text-sm text-muted-foreground">
      <p>{pt ? "JWT usa Authorization: Bearer; API key usa X-API-Key. Rotas de sessão admin recusam API key, inclusive com JWT. A identidade do host é separada das credenciais de usuário." : "JWT uses Authorization: Bearer; API keys use X-API-Key. Admin session routes reject API keys, including alongside JWT. Host identity is separate from user credentials."}</p>
      <p>{pt ? "Obrigatório indica validação estrutural; regras condicionais estão nas notas. As respostas declaradas podem ser acompanhadas por erros de autenticação, autorização e infraestrutura. Um esquema object livre não promete campos fixos. DELETE 204 não tem corpo; TXT/VTT/SRT/PDF e SSE usam seus próprios formatos." : "Required indicates structural validation; conditional requirements are in the notes. Declared responses can be accompanied by authentication, authorization and infrastructure errors. A free object schema does not promise fixed fields. DELETE 204 has no body; TXT/VTT/SRT/PDF and SSE use their own formats."}</p>
    </div>
    {groups.map((tag) => <section key={tag} className="space-y-3" aria-label={tag}>
      <h2 id={"group-" + tag.toLowerCase().replace(/[^a-z0-9]+/g, "-")} className="text-xl font-semibold scroll-mt-24">{tag}</h2>
      {entries.filter(({ operation }) => (operation.tags?.[0] ?? "General") === tag).map(({ path, method, operation }) => <details key={operation.operationId} id={operation.operationId} data-api-operation={`${method.toUpperCase()} ${path}`} className="rounded-lg border p-4 scroll-mt-24">
        <summary className="cursor-pointer space-y-1"><span className="font-mono text-sm break-all"><strong>{method.toUpperCase()}</strong> {path}</span><span className="block text-sm text-muted-foreground">{operation.summary}</span></summary>
        <div className="space-y-4 pt-4">
          <p className="text-sm"><strong>{pt ? "Autorização:" : "Authorization:"}</strong> {access[operation["x-access"]]}</p>
          {operation.description && <details><summary className="text-sm cursor-pointer">{pt ? "Descrição do endpoint" : "Endpoint description"}</summary><div className="whitespace-pre-wrap break-words pt-3 text-sm text-muted-foreground">{operation.description}</div></details>}
          {operation["x-contract-notes"]?.map((note, index) => <p key={index} className="text-sm text-muted-foreground">{note}</p>)}
          {!!operation.parameters?.length && <Grid columns={pt ? ["Parâmetro", "Local", "Obrigatório", "Tipo", "Padrões/limites", "Descrição"] : ["Parameter", "Location", "Required", "Type", "Defaults/limits", "Description"]}
            rows={operation.parameters.map((parameter) => [<code key="name">{parameter.name}</code>, parameter.in,
              parameter.required ? (pt ? "sim" : "yes") : (pt ? "não" : "no"), <Type key="type" schema={parameter.schema} />,
              limits(parameter.schema ?? {}), parameter.description])} />}
          {operation.requestBody && <div className="space-y-3"><p className="text-sm font-medium">{pt ? "Corpo da solicitação" : "Request body"}{operation.requestBody.required ? " *" : ""}</p>
            {Object.entries(operation.requestBody.content).map(([media, content]) => <div key={media} className="space-y-2"><p className="font-mono text-sm">{media} · <Type schema={content.schema} /></p><Fields schema={content.schema ?? {}} pt={pt} /></div>)}
          </div>}
          <div className="space-y-2"><p className="text-sm font-medium">{pt ? "Respostas declaradas" : "Declared responses"}</p>
            <Grid columns={["Status", "Content-Type", pt ? "Esquema" : "Schema", pt ? "Descrição" : "Description"]}
              rows={Object.entries(operation.responses).flatMap(([status, response]) => Object.entries(response.content ?? { "—": {} }).map(([media, content]) => [status, media, <Type key="type" schema={content.schema} />, response.description]))} />
          </div>
        </div>
      </details>)}
    </section>)}
    <section className="space-y-4"><h2 id="websockets" className="text-xl font-semibold scroll-mt-24">WebSocket</h2>
      {(spec["x-websockets"] ?? []).map((ws) => <div key={ws.path} className="rounded-lg border p-4 space-y-3 text-sm"><code className="break-all">WS {ws.path}</code><p>{ws.authentication}</p><p>{ws.protocol}</p><a className="text-primary underline" href={`${pt ? "/pt" : ""}/docs/live`}>{pt ? "Protocolo completo" : "Complete protocol"}</a></div>)}
    </section>
    <section className="space-y-3"><h2 id="models" className="text-xl font-semibold scroll-mt-24">{pt ? "Modelos e validação" : "Models and validation"}</h2>
      {Object.entries(spec.components.schemas).sort(([a], [b]) => a.localeCompare(b)).map(([name, model]) => <details key={name} id={"model-" + name} className="rounded-lg border p-4 scroll-mt-24">
        <summary className="cursor-pointer font-mono text-sm break-all">{name}</summary><div className="space-y-3 pt-4">
          {model.description && <p className="text-sm text-muted-foreground">{model.description}</p>}<Fields schema={model} pt={pt} />
          <pre className="max-w-full overflow-x-auto rounded-md bg-muted p-3 text-xs"><code>{JSON.stringify(model, null, 2)}</code></pre>
        </div>
      </details>)}
    </section>
  </section>;
}
