/** Public URLs used by statically rendered docs, independently of browser auth. */
const DEFAULT_SITE = "https://dev.ingestify.ai";
export const DOCS_ORIGIN = new URL(
  process.env.NEXT_PUBLIC_SITE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    DEFAULT_SITE,
  DEFAULT_SITE,
).origin;
export const DOCS_API_URL = new URL(
  process.env.NEXT_PUBLIC_API_URL || "/api",
  DOCS_ORIGIN,
).href.replace(/\/$/, "");
