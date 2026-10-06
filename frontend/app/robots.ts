import type { MetadataRoute } from "next";
import { DOCS_ORIGIN } from "./docs/config";
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${DOCS_ORIGIN}/sitemap.xml`,
  };
}
