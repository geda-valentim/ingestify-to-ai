import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";
export const metadata: Metadata = {
  title: "Ingestify — Data Engineering & AI-ready conversion",
  description:
    "Convert documents, images and recordings into AI-ready text and metadata. Use standalone conversions or build self-hosted Data Engineering pipelines.",
};
export default function Home() {
  return <LandingPage />;
}
