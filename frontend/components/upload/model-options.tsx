"use client";

import { useId, useState, useEffect } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import type { ParameterSchema } from "@/types/api";

/** Render parameters supplied by the API, preserving omitted worker defaults. */
export function ModelOptions({ schema, value, onChange, disabled = false, defaults = {}, onValid }: {
  schema: ParameterSchema; value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void; disabled?: boolean;
  defaults?: Record<string, unknown>;
  onValid?: (valid: boolean) => void;
}) {
  const prefix = useId();
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  useEffect(() => { onValid?.(!Object.entries(errors).some(([name, invalid]) => invalid && name in value)); }, [errors, value, onValid]);
  const set = (name: string, next: unknown) => {
    const result = { ...value };
    if (next === undefined) delete result[name]; else result[name] = next;
    onChange(result);
  };
  return <div className="grid gap-4 sm:grid-cols-2">
    {Object.entries(schema.properties ?? {}).filter(([, field]) => !field.readOnly).map(([name, original]) => {
      const resolve = (item: ParameterSchema): ParameterSchema => item.$ref ? schema.$defs?.[item.$ref.split("/").at(-1)!] ?? item : item;
      const resolved = resolve(original);
      const variants = (resolved.anyOf ?? original.anyOf)?.filter((item) => item.type !== "null").map(resolve);
      const field = variants?.find((item) => item.type !== "boolean") ?? variants?.[0] ?? resolved;
      const choices = resolved.enum ?? (resolved.const !== undefined ? [resolved.const] : undefined) ?? variants?.flatMap((item) => item.enum ?? (item.const !== undefined ? [item.const] : item.type === "boolean" ? [false, true] : []));
      const current = value[name];
      const defaultValue = defaults[name] ?? original.default;
      const id = `${prefix}-${name}`;
      const complex = [resolved, ...(variants ?? [])].some((item) => item.type === "object" || item.type === "array");
      const objects = [resolved, ...(variants ?? [])].filter((item) => item.properties && Object.keys(item.properties).length);
      const discriminator = objects.some((item) => item.properties?.kind?.const !== undefined) ? "kind" : "engine_type";
      const objectKinds = objects.filter((item) => item.properties?.[discriminator]?.const !== undefined);
      const selectedKind = current && typeof current === "object" && !Array.isArray(current) ? (current as Record<string, unknown>)[discriminator] : undefined;
      const defaultKind = defaultValue && typeof defaultValue === "object" ? (defaultValue as Record<string, unknown>)[discriminator] : undefined;
      const object = objectKinds.find((item) => item.properties?.[discriminator]?.const === (selectedKind ?? defaultKind)) ?? objects[0];
      const reportValidity = (valid: boolean) => setErrors((previous) => previous[name] === !valid ? previous : { ...previous, [name]: !valid });
      return <div key={name} className={`space-y-1 ${object ? "sm:col-span-2" : ""}`}>
        <Label htmlFor={id}>{original.title ?? name.replaceAll("_", " ")}</Label>
        {object ? <div className="rounded border p-3">
          {objectKinds.length > 1 && <select aria-label={`${original.title ?? name} engine`} disabled={disabled} value={String(selectedKind ?? defaultKind ?? objectKinds[0].properties?.[discriminator]?.const)} onChange={(event) => set(name, { [discriminator]: event.target.value })} className="mb-3 h-10 w-full rounded border bg-background px-3 text-sm">
            {objectKinds.map((choice) => <option key={String(choice.properties?.[discriminator]?.const)} value={String(choice.properties?.[discriminator]?.const)} disabled={!!choice["x-unavailable-reason"]}>{choice.title ?? String(choice.properties?.[discriminator]?.const)}</option>)}
          </select>}
          {current && typeof current === "object" && !Array.isArray(current) ? <>
            <ModelOptions schema={{ ...object, $defs: schema.$defs }} defaults={defaultValue && typeof defaultValue === "object" ? defaultValue as Record<string, unknown> : {}} value={current as Record<string, unknown>} onChange={(next) => set(name, next)} disabled={disabled} onValid={reportValidity} />
            <button type="button" disabled={disabled} onClick={() => set(name, undefined)} className="mt-3 text-xs underline">Restaurar padrões</button>
          </> : <button type="button" disabled={disabled} onClick={() => set(name, objectKinds.length ? { [discriminator]: defaultKind ?? objectKinds[0].properties?.[discriminator]?.const } : {})} className="text-sm underline">Configurar {original.title ?? name.replaceAll("_", " ")}</button>}
        </div> : complex ? <JsonOption id={id} disabled={disabled} value={current} defaultValue={defaultValue} onValid={reportValidity} onChange={(next) => set(name, next)} /> : choices?.length ? <select id={id} disabled={disabled || resolved.const !== undefined} value={resolved.const !== undefined ? JSON.stringify(resolved.const) : current === undefined ? "" : JSON.stringify(current)} onChange={(e) => set(name, e.target.value ? JSON.parse(e.target.value) : undefined)} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
          <option value="">Padrão{original.default !== undefined ? ` (${String(original.default)})` : " do serviço"}</option>
          {choices.map((choice) => <option key={JSON.stringify(choice)} value={JSON.stringify(choice)}>{String(choice)}</option>)}
        </select> : field.type === "boolean" ? <select id={id} disabled={disabled} value={current === undefined ? "" : String(current)} onChange={(e) => set(name, e.target.value === "" ? undefined : e.target.value === "true")} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
          <option value="">Padrão{original.default !== undefined ? ` (${original.default ? "sim" : "não"})` : " do serviço"}</option><option value="true">Sim</option><option value="false">Não</option>
        </select> : <Input id={id} disabled={disabled} type={field.type === "integer" || field.type === "number" ? "number" : "text"}
          step={field.type === "integer" ? 1 : "any"} min={field.minimum ?? field.exclusiveMinimum} max={field.maximum ?? field.exclusiveMaximum}
          placeholder={defaultValue != null ? `Padrão: ${String(defaultValue)}` : "Padrão do serviço"} value={current == null ? "" : String(current)}
          onChange={(e) => set(name, e.target.value === "" ? undefined : field.type === "integer" || field.type === "number" ? Number(e.target.value) : e.target.value)} />}
        {!complex && original.anyOf?.some((item) => item.type === "null") && <button type="button" disabled={disabled} className="text-xs underline" onClick={() => set(name, current === null ? undefined : null)}>{current === null ? "Restaurar padrão" : "Desativar (null)"}</button>}
        {original.description && <p className="text-xs text-muted-foreground">{original.description}</p>}
      </div>;
    })}
  </div>;
}

function JsonOption({ id, value, defaultValue, onChange, onValid, disabled }: { id: string; value: unknown; defaultValue: unknown; onChange: (value: unknown) => void; onValid: (valid: boolean) => void; disabled: boolean }) {
  const [draft, setDraft] = useState<{ raw: string; next: unknown; invalid: boolean } | null>(null);
  const active = draft && Object.is(value, draft.next);
  const displayed = active ? draft.raw : value === undefined ? "" : JSON.stringify(value);
  return <>
    <textarea id={id} disabled={disabled} className="min-h-20 w-full rounded border bg-background p-2 font-mono text-sm"
      placeholder={defaultValue === undefined ? 'JSON: objeto, lista ou texto entre aspas' : `Padrão: ${JSON.stringify(defaultValue)}`}
      value={displayed} onChange={(event) => {
        const text = event.target.value;
        try { const next = text.trim() ? JSON.parse(text) : undefined; setDraft({ raw: text, next, invalid: false }); onValid(true); onChange(next); }
        catch { setDraft({ raw: text, next: text, invalid: true }); onValid(false); onChange(text); }
      }} />
    {active && draft.invalid && <p role="alert" className="text-xs text-destructive">Informe JSON válido.</p>}
  </>;
}
