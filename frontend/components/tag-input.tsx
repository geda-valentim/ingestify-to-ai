"use client";

import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Tag as TagIcon, X } from "lucide-react";
import { tagsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { cn } from "@/lib/utils";

// Mirrors backend/shared/tags.py, so what the chip shows is what gets stored.
export const MAX_TAGS = 20;
const MAX_TAG_LENGTH = 50;

export function normalizeTag(raw: string): string {
  return raw.trim().replace(/^#+/, "").trim().replace(/\s+/g, " ").toLowerCase();
}

/** A tag rendered as a small pill. Clickable when `onClick` is given. */
export function TagChip({
  tag,
  onClick,
  onRemove,
  active,
  className,
}: {
  tag: string;
  onClick?: (e: React.MouseEvent) => void;
  onRemove?: () => void;
  active?: boolean;
  className?: string;
}) {
  const base = cn(
    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium max-w-[16rem]",
    active ? "border-primary bg-primary text-primary-foreground" : "bg-muted/60 text-foreground",
    onClick && !active && "hover:border-primary/60 hover:bg-primary/10",
    className
  );
  const content = (
    <>
      <TagIcon className="h-3 w-3 shrink-0 opacity-60" />
      <span className="truncate">{tag}</span>
    </>
  );

  return (
    <span className={base}>
      {onClick ? (
        <button type="button" onClick={onClick} className="inline-flex items-center gap-1 min-w-0">
          {content}
        </button>
      ) : (
        content
      )}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="-mr-1 rounded-full p-0.5 hover:bg-foreground/10"
          aria-label={`Remove tag ${tag}`}
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
}

/**
 * Free-form tag entry: Enter or comma adds, Backspace on an empty field removes
 * the last one. Suggests the tags already used on the user's other jobs.
 */
export function TagInput({
  value,
  onChange,
  id,
  placeholder = "Add tags: press Enter or comma",
  disabled,
  autoFocus,
}: {
  value: string[];
  onChange: (tags: string[]) => void;
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const token = useAuthStore((state) => state.token);
  const [draft, setDraft] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: known = [] } = useQuery({
    queryKey: ["tags", token],
    queryFn: () => tagsApi.list(),
    enabled: !!token,
    staleTime: 60_000,
  });

  const suggestions = useMemo(() => {
    const q = normalizeTag(draft);
    return known
      .map((t) => t.tag)
      .filter((t) => !value.includes(t) && (!q || t.includes(q)))
      .slice(0, 8);
  }, [known, value, draft]);

  const add = (raw: string) => {
    const next = [...value];
    for (const part of raw.split(",")) {
      const tag = normalizeTag(part).slice(0, MAX_TAG_LENGTH);
      if (tag && !next.includes(tag) && next.length < MAX_TAGS) next.push(tag);
    }
    if (next.length !== value.length) onChange(next);
    setDraft("");
  };

  const remove = (tag: string) => onChange(value.filter((t) => t !== tag));

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      if (draft.trim()) {
        e.preventDefault();
        add(draft);
      } else if (e.key === ",") {
        e.preventDefault();
      }
    } else if (e.key === "Backspace" && !draft && value.length) {
      remove(value[value.length - 1]);
    }
  };

  const full = value.length >= MAX_TAGS;

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "flex min-h-10 w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-sm",
          focused && "ring-2 ring-ring ring-offset-2 ring-offset-background",
          disabled && "opacity-50"
        )}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag) => (
          <TagChip key={tag} tag={tag} onRemove={disabled ? undefined : () => remove(tag)} />
        ))}
        <input
          ref={inputRef}
          id={id}
          autoFocus={autoFocus}
          value={draft}
          disabled={disabled || full}
          onChange={(e) => {
            // A pasted "a, b, c" becomes three tags at once.
            if (e.target.value.includes(",")) add(e.target.value);
            else setDraft(e.target.value);
          }}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            if (draft.trim()) add(draft);
          }}
          placeholder={value.length ? "" : full ? "" : placeholder}
          className="flex-1 min-w-[8rem] bg-transparent py-0.5 outline-none placeholder:text-muted-foreground"
        />
      </div>
      {focused && suggestions.length > 0 && !full && (
        // preventDefault on mousedown keeps the input focused, so the click lands.
        <div className="flex flex-wrap items-center gap-1.5" onMouseDown={(e) => e.preventDefault()}>
          <span className="text-xs text-muted-foreground">Used before:</span>
          {suggestions.map((tag) => (
            <TagChip
              key={tag}
              tag={tag}
              onClick={() => add(tag)}
              className="cursor-pointer"
            />
          ))}
        </div>
      )}
    </div>
  );
}
