import { DocsBrowser } from "../../docs/docs-browser";
import { docsMetadata } from "../../docs/metadata";

export const dynamic = "error";
export const metadata = docsMetadata("pt");
export default function PortugueseDocsPage() {
  return <DocsBrowser lang="pt" />;
}
