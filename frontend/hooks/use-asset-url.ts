"use client";

import { useEffect, useState } from "react";
import { jobsApi } from "@/lib/api";

export type AssetUrlState =
  | { state: "loading"; url: null; blob: null }
  | { state: "ready"; url: string; blob: Blob }
  /** 404 / 410 SOURCE_PURGED: deleted (purge_source retention, DELETE /jobs/{id}/source) or never stored */
  | { state: "unavailable"; url: null; blob: null }
  | { state: "error"; url: null; blob: null };

const LOADING: AssetUrlState = { state: "loading", url: null, blob: null };

/**
 * An image asset of a conversion (`GET /jobs/{job_id}/assets/{name}`) as a blob URL.
 *
 * The route needs the user's credentials, which an <img src> cannot send, so the
 * PNG is fetched with them and shown from an object URL, revoked on unmount or
 * when the asset changes. `enabled=false` fetches nothing (stays "loading").
 */
export function useAssetUrl(jobId: string | null, name: string | null, enabled = true): AssetUrlState {
  const [value, setValue] = useState<AssetUrlState>(LOADING);

  useEffect(() => {
    if (!jobId || !name || !enabled) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setValue(LOADING);
    jobsApi
      .getAssetBlob(jobId, name, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        if (!blob) {
          setValue({ state: "unavailable", url: null, blob: null });
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setValue({ state: "ready", url: objectUrl, blob });
      })
      .catch(() => {
        if (!controller.signal.aborted) setValue({ state: "error", url: null, blob: null });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [jobId, name, enabled]);

  return value;
}

/** `/jobs/{job_id}/assets/{name}` (a relative API path, as the Markdown and `assets[].url` carry it). */
const ASSET_PATH = /^\/jobs\/([^/?#]+)\/assets\/([^/?#]+)$/;

export function parseAssetPath(src: unknown): { jobId: string; name: string } | null {
  const match = typeof src === "string" ? ASSET_PATH.exec(src) : null;
  if (!match) return null;
  try {
    return { jobId: decodeURIComponent(match[1]), name: decodeURIComponent(match[2]) };
  } catch {
    return null;
  }
}
