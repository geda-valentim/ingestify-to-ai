import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";
export const metadata: Metadata = {
  title: "Ingestify — Your files, AI-ready",
  description:
    "Turn documents, images and recordings into information your applications can use. Explore operations, the API and local or optional cloud transcription.",
};
export default function Home() {
  return <LandingPage />;
}
