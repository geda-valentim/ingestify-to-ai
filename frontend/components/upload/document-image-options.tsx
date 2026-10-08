"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { DocumentImageOptions } from "@/types/api";

/**
 * The image options of a document conversion (/upload and /convert accept them for
 * every source type): extract the pictures (image_mode=referenced) and/or render
 * every PDF page (page_images). Both default off, so the request is unchanged.
 *
 * `purgeSource` is whether this request also deletes the original: with it the
 * images do not live as long as the job, they expire ASSET_RETENTION_SECONDS after
 * it ends (1 hour by default; the browser does not know the server's value).
 */
export function DocumentImageFields({
  idPrefix,
  value,
  onChange,
  disabled,
  purgeSource,
}: {
  idPrefix: string;
  value: DocumentImageOptions;
  onChange: (next: DocumentImageOptions) => void;
  disabled?: boolean;
  purgeSource: boolean;
}) {
  const extract = value.image_mode === "referenced";
  const pages = value.page_images === true;
  const any = extract || pages;

  return (
    <fieldset className="space-y-3 rounded-md border p-3" data-testid={`${idPrefix}-image-options`}>
      <legend className="px-1 text-sm font-medium">Images</legend>
      <div className="flex items-start space-x-2">
        <Checkbox
          id={`${idPrefix}-extract-images`}
          checked={extract}
          onCheckedChange={(checked) => onChange({ ...value, image_mode: checked === true ? "referenced" : "none" })}
          disabled={disabled}
          className="mt-0.5"
        />
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-extract-images`} className="font-normal">
            Extract images
          </Label>
          <p className="text-xs text-muted-foreground">
            Every picture found in the document (figures, charts, photos) is saved as a PNG, shown in the
            Markdown and listed under Images on the job page. Very small pictures are skipped.
          </p>
        </div>
      </div>
      <div className="flex items-start space-x-2">
        <Checkbox
          id={`${idPrefix}-page-images`}
          checked={pages}
          onCheckedChange={(checked) => onChange({ ...value, page_images: checked === true })}
          disabled={disabled}
          className="mt-0.5"
        />
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-page-images`} className="font-normal">
            Render each page as an image
          </Label>
          <p className="text-xs text-muted-foreground">
            PDF only: every page is also saved as a PNG (not part of the Markdown). Use it for slides, scanned
            documents or pages that are a single image — a full-page image is not detected as a picture, so
            &quot;Extract images&quot; alone would miss it.
          </p>
        </div>
      </div>
      {any && (
        <p className="text-xs text-muted-foreground" data-testid={`${idPrefix}-image-retention`}>
          {purgeSource
            ? "Because the original file is not kept, the images stay available for a limited time after the job finishes (1 hour by default) so you can download them, and are then deleted. \"Delete original files\" on the job page deletes them right away."
            : "The images are kept as long as the job, until you delete the job or use \"Delete original files\" on the job page."}
        </p>
      )}
    </fieldset>
  );
}
