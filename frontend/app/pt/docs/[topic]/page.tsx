import { notFound } from "next/navigation";
import { DocsBrowser } from "../../../docs/docs-browser";
import { DOCS_TOPICS } from "../../../docs/topics";
import { docsMetadata } from "../../../docs/metadata";

type Props = { params: Promise<{ topic: string }> };
export const dynamic = "error";
export const dynamicParams = false;
export function generateStaticParams() {
  return DOCS_TOPICS.map(({ slug }) => ({ topic: slug }));
}
export async function generateMetadata({ params }: Props) {
  return docsMetadata("pt", (await params).topic);
}
export default async function DocsTopicPage({ params }: Props) {
  const { topic } = await params;
  if (!DOCS_TOPICS.some((item) => item.slug === topic)) notFound();
  return <DocsBrowser topic={topic} lang="pt" />;
}
