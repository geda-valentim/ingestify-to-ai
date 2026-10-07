"use client";
import { useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function CodeExamples({
  examples,
  label,
  copyLabel,
}: {
  examples: { label: string; code: string; note?: ReactNode }[];
  label: string;
  copyLabel: string;
}) {
  return (
    <Tabs defaultValue={examples[0].label} data-docs-code-examples className="min-w-0">
      <div className="overflow-x-auto">
        <TabsList aria-label={label} className="justify-start">
          {examples.map((example) => (
            <TabsTrigger key={example.label} value={example.label}>
              {example.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
      {examples.map((example) => (
        <TabsContent
          key={example.label}
          value={example.label}
          forceMount
          className="mt-3 data-[state=inactive]:hidden"
        >
          <h3 data-code-example-label className="hidden mb-2 text-sm font-medium">
            {example.label}
          </h3>
          <CodeBlock code={example.code} copyLabel={copyLabel} />
          {example.note && <p className="pt-2 text-sm text-muted-foreground">{example.note}</p>}
        </TabsContent>
      ))}
      <noscript>
        <style>{`
          [data-docs-code-examples] [role="tablist"] { display: none; }
          [data-docs-code-examples] [role="tabpanel"] { display: block !important; }
          [data-docs-code-examples] [data-code-example-label] { display: block; }
        `}</style>
      </noscript>
    </Tabs>
  );
}

export function CodeBlock({
  code,
  copyLabel,
}: {
  code: string;
  copyLabel: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (insecure origin); the code stays selectable.
    }
  };

  return (
    <div className="relative">
      <pre className="bg-muted p-4 pr-12 rounded-lg overflow-x-auto text-sm leading-relaxed">
        <code>{code}</code>
      </pre>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={copy}
        className="absolute top-2 right-2 h-8 w-8 p-0"
        aria-label={copyLabel}
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </Button>
    </div>
  );
}
