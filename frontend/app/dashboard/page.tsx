import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { DashboardOverview } from "./overview";

export const metadata: Metadata = {
  title: "Dashboard | Ingestify",
  robots: { index: false, follow: false },
};

export default async function DashboardPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  // Preserve bookmarked upload links and their project/folder context.
  if (["project_id", "folder_id", "project", "folder"].some(key => params[key] !== undefined)) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) value.forEach(item => query.append(key, item));
      else if (value !== undefined) query.set(key, value);
    }
    redirect(`/convert?${query}`);
  }
  return <DashboardOverview />;
}
