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
