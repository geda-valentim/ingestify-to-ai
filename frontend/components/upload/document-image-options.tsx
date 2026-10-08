"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { DoclingPreset, DocumentImageOptions } from "@/types/api";

const PRESETS: { value: DoclingPreset; label: string; help: string }[] = [
  {
    value: "fast",
    label: "Fast",
    help: "Text and tables, no OCR (~35 s per MB). Best for digital PDFs.",
  },
  {
    value: "balanced",
    label: "Balanced",
    help: "Also builds the document's picture images, no OCR (~70–105 s per MB).",
  },
  {
    value: "quality",
    label: "Quality",
    help: "OCR for scanned PDFs, plus pictures and tables (~350 s per MB, much slower).",
  },
];

function OptionCheckbox({
  id,
  checked,
  onChange,
  disabled,
  label,
  children,
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start space-x-2">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(next) => onChange(next === true)}
        disabled={disabled}
        className="mt-0.5"
      />
      <div className="space-y-1">
        <Label htmlFor={id} className="font-normal">
          {label}
        </Label>
        <p className="text-xs text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

/**
 * Every PDF/document option of a conversion in one group (/upload and /convert
 * accept them for every source type): the Docling preset, extract the pictures
 * (image_mode=referenced), render every PDF page (page_images), describe / OCR
 * the figures inline in the Markdown (describe_images / ocr_images) and delete
 * the original (purge_source). All default off / "fast", so an untouched form
 * sends the same request as before.
 *
 * With purge_source the images do not live as long as the job, they expire
 * ASSET_RETENTION_SECONDS after it ends (1 hour by default; the browser does not
 * know the server's value).
 */
export function DocumentImageFields({
  idPrefix,
  value,
  onChange,
  disabled,
  purgeSource,
  onPurgeSourceChange,
}: {
  idPrefix: string;
  value: DocumentImageOptions;
  onChange: (next: DocumentImageOptions) => void;
  disabled?: boolean;
  purgeSource: boolean;
  onPurgeSourceChange: (next: boolean) => void;
}) {
  const preset = value.docling_preset ?? "fast";
  const extract = value.image_mode === "referenced";
  const pages = value.page_images === true;
  const describe = value.describe_images === true;
  const ocr = value.ocr_images === true;
  const any = extract || pages;

  return (
    <fieldset className="space-y-4 rounded-md border p-3" data-testid={`${idPrefix}-image-options`}>
      <legend className="px-1 text-sm font-medium">PDF options</legend>

      <div className="space-y-2">
        <p className="text-sm" id={`${idPrefix}-preset-label`}>
          Conversion preset
        </p>
        <div
          className="grid grid-cols-1 gap-2 sm:grid-cols-3"
          role="radiogroup"
          aria-labelledby={`${idPrefix}-preset-label`}
          data-testid={`${idPrefix}-preset`}
        >
          {PRESETS.map((option) => {
            const selected = option.value === preset;
            return (
              <button
                key={option.value}
                id={`${idPrefix}-preset-${option.value}`}
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={disabled}
                // "fast" is the default: leaving it out keeps the request (and the
                // server's dedup key) identical to one sent without a preset
                onClick={() => onChange({ ...value, docling_preset: option.value === "fast" ? undefined : option.value })}
                className={cn(
                  "rounded-md border p-2 text-left transition-colors disabled:opacity-50",
                  selected ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-muted/50"
                )}
              >
                <span className="block text-sm font-medium">
                  {option.label}
                  {option.value === "fast" && <span className="font-normal text-muted-foreground"> (default)</span>}
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">{option.help}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-3">
        <p className="text-sm">Images</p>
        <OptionCheckbox
          id={`${idPrefix}-extract-images`}
          checked={extract}
          onChange={(checked) => onChange({ ...value, image_mode: checked ? "referenced" : "none" })}
          disabled={disabled}
          label="Extract images"
        >
          Every picture found in the document (figures, charts, photos) is saved as a PNG, shown in the Markdown
          and listed under Images on the job page. Very small pictures are skipped.
        </OptionCheckbox>
        <OptionCheckbox
          id={`${idPrefix}-page-images`}
          checked={pages}
          onChange={(checked) => onChange({ ...value, page_images: checked })}
          disabled={disabled}
          label="Render each page as an image"
        >
          PDF only: every page is also saved as a PNG (not part of the Markdown). Use it for slides, scanned
          documents or pages that are a single image — a full-page image is not detected as a picture, so
          &quot;Extract images&quot; alone would miss it.
        </OptionCheckbox>
        {any && (
          <p className="text-xs text-muted-foreground" data-testid={`${idPrefix}-image-retention`}>
            {purgeSource
              ? "Because the original file is not kept, the images stay available for a limited time after the job finishes (1 hour by default) so you can download them, and are then deleted. \"Delete original files\" on the job page deletes them right away."
              : "The images are kept as long as the job, until you delete the job or use \"Delete original files\" on the job page."}
          </p>
        )}
      </div>

      <div className="space-y-3">
        <p className="text-sm">Figures</p>
        <OptionCheckbox
          id={`${idPrefix}-describe-images`}
          checked={describe}
          onChange={(checked) => onChange({ ...value, describe_images: checked })}
          disabled={disabled}
          label="Describe figures"
        >
          Each figure gets a short description written by a vision model, right below it in the Markdown.
          Descriptions are in English for now.
        </OptionCheckbox>
        <OptionCheckbox
          id={`${idPrefix}-ocr-images`}
          checked={ocr}
          onChange={(checked) => onChange({ ...value, ocr_images: checked })}
          disabled={disabled}
          label="OCR text in figures"
        >
          The text inside each figure (labels, chart axes, screenshots) is read and added right below it in the
          Markdown.
        </OptionCheckbox>
        {(describe || ocr) && (
          <p className="text-xs text-muted-foreground" data-testid={`${idPrefix}-figure-note`}>
            Works with or without &quot;Extract images&quot;. Only figures are read, never page renders; identical
            images are processed once, and very small ones or those past the per-document limit (50 by default) are
            skipped. The job takes longer: it stays processing until the text is in the Markdown.
          </p>
        )}
      </div>

      <OptionCheckbox
        id={`${idPrefix}-purge-source`}
        checked={purgeSource}
        onChange={onPurgeSourceChange}
        disabled={disabled}
        label="Don't keep the original file after converting"
      >
        The file and its page PDFs are deleted when the job finishes (also when it fails, after its automatic
        retries{describe || ocr ? "; with figure descriptions, only once they are in the Markdown" : ""}). The
        Markdown result is kept, and failed pages can no longer be retried. Extracted images are kept for a limited
        time so you can download them.
      </OptionCheckbox>
    </fieldset>
  );
}
