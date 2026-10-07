import Link from "next/link";
import { Badge } from "@/components/ui/badge";

export function Endpoint({ method, path }: { method: string; path: string }) {
  return (
    <div className="flex items-center gap-2 font-mono text-sm">
      <Badge variant={method === "GET" ? "secondary" : "default"}>
        {method}
      </Badge>
      <span className="break-all">{path}</span>
    </div>
  );
}

export function Table({
  head,
  rows,
}: {
  head?: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        {head && (
          <thead className="bg-muted/50">
            <tr>
              {head.map((h) => (
                <th
                  key={h}
                  className="text-left font-medium px-3 py-2 whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={`align-top ${head || i > 0 ? "border-t" : ""}`}
            >
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {children}
    </section>
  );
}

export function Subheading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-lg font-semibold pt-2">{children}</h2>;
}

export function P({
  children,
  small,
}: {
  children: React.ReactNode;
  small?: boolean;
}) {
  return (
    <p
      className={
        small ? "text-sm text-muted-foreground" : "text-muted-foreground"
      }
    >
      {children}
    </p>
  );
}

export function C({ children }: { children: React.ReactNode }) {
  return (
    <code className="bg-muted px-1.5 py-0.5 rounded text-[0.85em]">
      {children}
    </code>
  );
}

export function A({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  const className = "text-primary underline underline-offset-4";
  return href.startsWith("/") ? (
    <Link href={href} className={className}>
      {children}
    </Link>
  ) : (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children}
    </a>
  );
}
