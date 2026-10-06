import { DocsBrowser } from "./docs-browser";
import { docsMetadata } from "./metadata";

export const dynamic = "error";
export const metadata = docsMetadata("en");
export default function DocsPage() {
  return <DocsBrowser lang="en" />;
}
