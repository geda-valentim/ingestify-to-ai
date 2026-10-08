"use client";

import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Download, ImageOff, Loader2 } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { assetLabel, countAssetKinds, storeZip } from "@/lib/conversion-assets";
import { formatBytes, parseApiDate } from "@/lib/utils";
import { parseAssetPath, useAssetUrl } from "@/hooks/use-asset-url";
import { useToast } from "@/hooks/use-toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ConversionAsset, ConversionAssetsSkipped, JobStatusResponse } from "@/types/api";

/** Thumbnails are fetched one request each: show them a page at a time. */
const PAGE_SIZE = 24;

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** The job that owns an asset: its `url` always points at the MAIN job. */
function assetJobId(asset: ConversionAsset, fallback: string) {
  return parseAssetPath(asset.url)?.jobId ?? fallback;
}

function AssetCard({ asset, jobId, available }: { asset: ConversionAsset; jobId: string; available: boolean }) {
  const { toast } = useToast();
  const owner = assetJobId(asset, jobId);
  const loaded = useAssetUrl(owner, asset.name, available);
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    if (loaded.state === "ready") {
      saveBlob(loaded.blob, asset.name);
      return;
    }
    setDownloading(true);
    try {
      const blob = await jobsApi.getAssetBlob(owner, asset.name);
      if (blob) saveBlob(blob, asset.name);
      else toast({ title: "Image no longer available", description: asset.name, variant: "destructive" });
    } catch (error) {
      toast({ title: "Could not download the image", description: String(error), variant: "destructive" });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <figure className="flex flex-col overflow-hidden rounded-lg border bg-background" data-testid="job-asset">
      <div className="flex aspect-[4/3] items-center justify-center bg-muted/40">
        {loaded.state === "ready" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={loaded.url} alt={assetLabel(asset)} className="max-h-full max-w-full object-contain" />
        ) : loaded.state === "loading" && available ? (
          <div className="h-full w-full animate-pulse bg-muted" aria-label="Loading image" />
        ) : (
          <div className="flex flex-col items-center gap-1 p-2 text-center text-xs text-muted-foreground">
            <ImageOff className="h-5 w-5" />
            Image unavailable
          </div>
        )}
      </div>
      <figcaption className="space-y-1 p-2 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium truncate">{assetLabel(asset)}</span>
          <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px]">
            {asset.kind === "page" ? "page" : "picture"}
          </Badge>
        </div>
        <p className="text-muted-foreground">
          {asset.width}×{asset.height} px · {formatBytes(asset.size_bytes)}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="h-7 w-full text-xs"
          onClick={download}
          disabled={!available || downloading || loaded.state === "unavailable"}
          aria-label={`Download ${asset.name}`}
        >
          {downloading ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Download className="mr-1 h-3 w-3" />}
          PNG
        </Button>
      </figcaption>
    </figure>
  );
}

/**
 * The images of a conversion (image_mode=referenced pictures and page_images
 * renders), from `assets` of GET /jobs/{id}/result, loaded with the user's
 * credentials. They can expire (purge_source + ASSET_RETENTION_SECONDS) or be
 * deleted ("Delete original files"): GET /jobs/{id} says so with
 * assets_available / assets_expire_at, and the route then answers 410.
 */
export function JobImages({
  status,
  assets,
  skipped,
  fileName,
}: {
  status: JobStatusResponse;
  assets: ConversionAsset[];
  skipped?: ConversionAssetsSkipped | null;
  fileName: string;
}) {
  const { toast } = useToast();
  const [shown, setShown] = useState(PAGE_SIZE);
  const [zipping, setZipping] = useState<{ done: number; total: number } | null>(null);
  // Older API versions do not send the field: assume available, the loader handles 410
  const available = status.assets_available !== false;
  const expiresAt = status.assets_expire_at ? parseApiDate(status.assets_expire_at) : null;
  const { pictures, pages } = countAssetKinds(assets);
  const skippedTotal = skipped
    ? skipped.too_small + skipped.count_limit + skipped.size_limit + skipped.unavailable
    : 0;

  const downloadAll = async () => {
    setZipping({ done: 0, total: assets.length });
    try {
      const files: { name: string; data: Uint8Array }[] = [];
      let missing = 0;
      for (const asset of assets) {
        const blob = await jobsApi.getAssetBlob(assetJobId(asset, status.job_id), asset.name);
        if (blob) files.push({ name: asset.name, data: new Uint8Array(await blob.arrayBuffer()) });
        else missing += 1;
        setZipping({ done: files.length + missing, total: assets.length });
      }
      if (!files.length) {
        toast({ title: "The images are no longer available", variant: "destructive" });
        return;
      }
      const zip = storeZip(files);
      saveBlob(new Blob([zip.buffer as ArrayBuffer], { type: "application/zip" }), `${fileName}-images.zip`);
      if (missing) toast({ title: `${missing} image${missing > 1 ? "s" : ""} could not be included` });
    } catch (error) {
      toast({ title: "Could not download the images", description: String(error), variant: "destructive" });
    } finally {
      setZipping(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="job-images">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1 text-sm">
          <p className="font-medium">
            {[pictures && `${pictures} extracted picture${pictures > 1 ? "s" : ""}`, pages && `${pages} page image${pages > 1 ? "s" : ""}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {!available ? (
            <p className="text-muted-foreground" data-testid="job-images-deleted">
              These images were deleted
              {status.source_deleted_at ? " with the original files" : ""} and can no longer be downloaded.
            </p>
          ) : expiresAt ? (
            <p className="text-muted-foreground" data-testid="job-images-expiry">
              Available until {expiresAt.toLocaleString()} ({formatDistanceToNow(expiresAt, { addSuffix: true })}):
              the original was not kept, so the images are deleted after a retention period. Download what you need.
            </p>
          ) : (
            <p className="text-muted-foreground">
              Kept with the job. &quot;Delete original files&quot; deletes them too.
            </p>
          )}
          {skippedTotal > 0 && (
            <p className="text-xs text-muted-foreground">
              {skippedTotal} picture{skippedTotal > 1 ? "s were" : " was"} not saved (
              {[
                skipped!.too_small && `${skipped!.too_small} too small`,
                skipped!.count_limit && `${skipped!.count_limit} over the count limit`,
                skipped!.size_limit && `${skipped!.size_limit} over the size limit`,
                skipped!.unavailable && `${skipped!.unavailable} unavailable`,
              ]
                .filter(Boolean)
                .join(", ")}
              ) and stay as a placeholder in the Markdown.
            </p>
          )}
        </div>
        {available && assets.length > 1 && (
          <Button size="sm" onClick={downloadAll} disabled={!!zipping}>
            {zipping ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {zipping.done}/{zipping.total}
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                Download all (.zip)
              </>
            )}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        {assets.slice(0, shown).map((asset) => (
          <AssetCard key={asset.name} asset={asset} jobId={status.job_id} available={available} />
        ))}
      </div>
      {assets.length > shown && (
        <div className="text-center">
          <Button variant="outline" size="sm" onClick={() => setShown((n) => n + PAGE_SIZE)}>
            Show more ({assets.length - shown} left)
          </Button>
        </div>
      )}
    </div>
  );
}
