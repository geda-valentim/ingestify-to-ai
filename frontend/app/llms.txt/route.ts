import { DOCS_ORIGIN, DOCS_API_URL } from "../docs/config";
import { DOCS_TOPICS, docsHref } from "../docs/topics";
export const dynamic = "force-static";
export function GET() {
  const text = [
    "# Ingestify",
    "",
    "> Self-hosted conversion of documents, images and recordings into data for AI and Data Engineering workflows.",
    "",
    "Documentation pages contain static HTML and can be read without JavaScript. Examples are illustrative; consult the OpenAPI schema for request and response contracts.",
    "",
    "## Agent integration",
    `- [Ingestify for agents](${DOCS_ORIGIN}/agents): HTTP tool workflows for ingesting, tracking, reading and searching data.`,
    "",
    "## Documentation",
    `- [Overview](${DOCS_ORIGIN}/docs): English documentation index.`,
    ...DOCS_TOPICS.map(
      (topic) =>
        `- [${topic.title.en}](${DOCS_ORIGIN}${docsHref(topic.slug, "en")})`,
    ),
    "",
    "## API reference",
    `- [OpenAPI JSON](${DOCS_API_URL}/openapi.json): Public machine-readable API schema.`,
    `- [Swagger UI](${DOCS_API_URL}/docs): Interactive API reference; requires JavaScript.`,
    "",
    "## Other languages",
    `- [Documentação em português](${DOCS_ORIGIN}/pt/docs)`,
    "",
  ].join("\n");
  return new Response(text, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
