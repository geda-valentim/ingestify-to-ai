"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NameResolveResponse } from "@/types/api";

/**
 * What the user picked: an existing project/folder (`id` set) or a name typed
 * to be created by the upload's get-or-add (`id: null`).
 */
export interface LocationChoice {
  id: string | null;
  name: string;
}

export interface LocationOption {
  id: string;
  name: string;
  count?: number;
}

type Item =
  | { kind: "match"; id: string; name: string }
  | { kind: "create"; name: string }
  | { kind: "option"; option: LocationOption };

const RESOLVE_DEBOUNCE_MS = 250;
const MAX_LISTED = 50;

/**
 * Type-to-pick-or-create combobox (input + its own listbox, keyboard driven,
 * in the style of `tag-input.tsx`).
 *
 * The list is filtered by a plain substring only to *show* options. Whether the
 * typed text is an existing project/folder is asked to the backend (`resolve`):
 * its normalisation rule (accents, case, Unicode) is deliberately not mirrored
 * here, so "reuniao semanal" can resolve to "Reunião Semanal".
 */
export function LocationCombobox({
  id,
  value,
  onChange,
  options,
  resolve,
  resolveKey,
  noun,
  allowCreate = true,
  placeholder,
  disabled,
  autoFocus,
  invalid,
}: {
  id?: string;
  value: LocationChoice | null;
  onChange: (value: LocationChoice | null) => void;
  options: LocationOption[];
  resolve: (name: string) => Promise<NameResolveResponse>;
  /** react-query key prefix for `resolve` (the typed name is appended). */
  resolveKey: unknown[];
  /** "project" or "folder", for the copy. */
  noun: string;
  /** False where nothing can be created (e.g. rebinding an API key). */
  allowCreate?: boolean;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  invalid?: boolean;
}) {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState(value?.name ?? "");
  const [debounced, setDebounced] = useState(draft.trim());
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  // Typing clears the selection; that must not wipe what is being typed.
  const clearedByTyping = useRef(false);

  useEffect(() => {
    if (value === null && clearedByTyping.current) {
      clearedByTyping.current = false;
      return;
    }
    clearedByTyping.current = false;
    setDraft(value?.name ?? "");
  }, [value?.id, value?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = setTimeout(() => setDebounced(draft.trim()), RESOLVE_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [draft]);

  const resolved = useQuery({
    queryKey: [...resolveKey, "resolve", debounced],
    queryFn: () => resolve(debounced),
    enabled: !disabled && debounced.length > 0,
    staleTime: 30_000,
  });
  const typed = draft.trim();
  const fresh = resolved.data && debounced === typed ? resolved.data : null;
  const checking = typed.length > 0 && (debounced !== typed || resolved.isFetching) && !fresh;

  // A name committed as "new" that the backend says already exists becomes that
  // project/folder, so the "new" badge never lies.
  useEffect(() => {
    if (value && value.id === null && fresh?.valid && fresh.match && debounced === value.name.trim()) {
      onChange({ id: fresh.match.id, name: fresh.match.name });
    }
  }, [fresh, value, debounced, onChange]);

  const items = useMemo<Item[]>(() => {
    const q = typed.toLowerCase();
    const showAll = !q || (value !== null && typed === value.name);
    const matchId = fresh?.valid ? fresh.match?.id : undefined;
    const listed = options
      .filter((o) => o.id !== matchId && (showAll || o.name.toLowerCase().includes(q)))
      .slice(0, MAX_LISTED)
      .map<Item>((option) => ({ kind: "option", option }));
    const head: Item[] = [];
    if (typed && fresh?.valid && !(value && typed === value.name)) {
      if (fresh.match) head.push({ kind: "match", id: fresh.match.id, name: fresh.match.name });
      else if (allowCreate) head.push({ kind: "create", name: typed });
    }
    return [...head, ...listed];
  }, [options, typed, fresh, value, allowCreate]);

  useEffect(() => setHighlight(0), [typed, items.length]);

  const select = (item: Item) => {
    const next: LocationChoice =
      item.kind === "option"
        ? { id: item.option.id, name: item.option.name }
        : item.kind === "match"
          ? { id: item.id, name: item.name }
          : { id: null, name: item.name };
    onChange(next);
    setDraft(next.name);
    setOpen(false);
  };

  // Leaving the field with text typed but not picked: take what it resolves to,
  // or the text itself (the upload's get-or-add will create it).
  const commitDraft = () => {
    if (!typed || (value && typed === value.name)) return;
    if (fresh?.valid && fresh.match) select({ kind: "match", id: fresh.match.id, name: fresh.match.name });
    else if (allowCreate && (!fresh || fresh.valid)) select({ kind: "create", name: typed });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) setOpen(true);
      else setHighlight((h) => Math.min(h + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      if (open && items[highlight]) {
        e.preventDefault();
        select(items[highlight]);
      } else if (typed && !(value && typed === value.name)) {
        e.preventDefault();
        commitDraft();
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
      }
    }
  };

  const errorText = typed && fresh && !fresh.valid ? fresh.error || `Invalid ${noun} name` : null;
  const notFound = typed && fresh?.valid && !fresh.match && !allowCreate && !(value && typed === value.name);
  const isNew = value !== null && value.id === null;
  const activeId = open && items[highlight] ? `${listId}-${highlight}` : undefined;

  return (
    <div className="relative">
      <div
        className={cn(
          "flex h-10 w-full items-center gap-2 rounded-md border border-input bg-background px-3 text-sm ring-offset-background",
          "focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2",
          (invalid || errorText) && "border-destructive",
          disabled && "cursor-not-allowed opacity-50"
        )}
      >
        <input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          aria-invalid={invalid || !!errorText || undefined}
          autoComplete="off"
          autoFocus={autoFocus}
          disabled={disabled}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => {
            setDraft(e.target.value);
            setOpen(true);
            if (value !== null && e.target.value !== value.name) {
              clearedByTyping.current = true;
              onChange(null);
            }
          }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onBlur={() => {
            setOpen(false);
            commitDraft();
          }}
          onKeyDown={onKeyDown}
          className="min-w-0 flex-1 bg-transparent py-2 outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
        />
        {isNew && (
          <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
            new
          </span>
        )}
        {checking && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />}
        {(value || draft) && !disabled ? (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              setDraft("");
              onChange(null);
              inputRef.current?.focus();
            }}
            className="shrink-0 rounded-sm text-muted-foreground hover:text-foreground"
            aria-label={`Clear ${noun}`}
          >
            <X className="h-4 w-4" />
          </button>
        ) : (
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
        )}
      </div>

      {open && !disabled && (items.length > 0 || checking || errorText || notFound) && (
        // preventDefault on mousedown keeps the input focused, so the click lands.
        <ul
          id={listId}
          role="listbox"
          onMouseDown={(e) => e.preventDefault()}
          className="absolute z-30 mt-1 max-h-64 w-full overflow-y-auto rounded-md border bg-popover p-1 text-sm text-popover-foreground shadow-md"
        >
          {checking && items.length === 0 && (
            <li className="flex items-center gap-2 px-2 py-1.5 text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Checking…
            </li>
          )}
          {errorText && <li className="px-2 py-1.5 text-destructive">{errorText}</li>}
          {notFound && (
            <li className="px-2 py-1.5 text-muted-foreground">
              No {noun} named “{typed}”
            </li>
          )}
          {items.map((item, i) => (
            <li
              key={item.kind === "option" ? item.option.id : `${item.kind}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === highlight}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => select(item)}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5",
                i === highlight && "bg-accent text-accent-foreground"
              )}
            >
              {item.kind === "create" ? (
                <>
                  <Plus className="h-3.5 w-3.5 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate">
                    Create <span className="font-medium">“{item.name}”</span>
                  </span>
                  <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                    new
                  </span>
                </>
              ) : item.kind === "match" ? (
                <>
                  <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate">
                    Use <span className="font-medium">“{item.name}”</span>
                  </span>
                </>
              ) : (
                <>
                  <Check
                    className={cn("h-3.5 w-3.5 shrink-0", value?.id === item.option.id ? "opacity-100" : "opacity-0")}
                  />
                  <span className="min-w-0 flex-1 truncate">{item.option.name}</span>
                  {item.option.count !== undefined && (
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{item.option.count}</span>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {errorText && !open && <p className="mt-1 text-xs text-destructive">{errorText}</p>}
    </div>
  );
}
