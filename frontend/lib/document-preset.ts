import type { DoclingPreset } from "@/types/api";

/** The preset the form shows selected when the user has not touched it. */
export const DEFAULT_DOCLING_PRESET: DoclingPreset = "fast";

/**
 * The preset a document conversion is sent with. Always explicit: an omitted
 * preset makes the server apply its own defaults (DOCLING_ENABLE_* settings),
 * which may differ from the "Fast" the form shows as selected.
 */
export function effectiveDoclingPreset(preset: DoclingPreset | undefined): DoclingPreset {
  return preset ?? DEFAULT_DOCLING_PRESET;
}
