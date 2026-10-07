"use client";

import { useState } from "react";
import { Check, Copy, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CopyButton({
  text,
  label = "Copy",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          // Clipboard needs a secure origin (https or localhost); over plain
          // http on the LAN it is unavailable and the text stays selectable.
        }
      }}
    >
      {copied ? (
        <Check className="h-4 w-4 mr-2" />
      ) : (
        <Copy className="h-4 w-4 mr-2" />
      )}
      {copied ? "Copied" : label}
    </Button>
  );
}

export function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="border rounded-lg bg-muted/30 p-4 md:p-6">{children}</div>
  );
}

export function Spinner() {
  return (
    <div className="py-12 flex items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
}
