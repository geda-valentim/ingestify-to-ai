import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formats API error responses into a user-friendly string message
 * Handles FastAPI validation errors and standard error responses
 */
export function formatApiError(error: any, fallbackMessage = "An error occurred"): string {
  // Check for standard error response with detail
  if (error?.response?.data?.detail) {
    const detail = error.response.data.detail;

    // If detail is a string, return it
    if (typeof detail === "string") {
      return detail;
    }

    // If detail is an array (Pydantic validation errors)
    if (Array.isArray(detail)) {
      return detail
        .map((err: any) => {
          // Format: "field: error message"
          const field = err.loc?.slice(1).join(".") || "field";
          return `${field}: ${err.msg}`;
        })
        .join(", ");
    }

    // If detail is an object, stringify it
    if (typeof detail === "object") {
      return JSON.stringify(detail);
    }
  }

  // Check for error message
  if (error?.message && typeof error.message === "string") {
    return error.message;
  }

  return fallbackMessage;
}

/** Save text as a file in the browser. */
export function downloadText(filename: string, content: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** Seconds as m:ss, or h:mm:ss from one hour up. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, "0")
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`
}

/** Bytes as a short human-readable size. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB"]
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`
}
