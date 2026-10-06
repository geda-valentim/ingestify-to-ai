import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";
export const metadata: Metadata = {
  title: "Ingestify — Data conversion for AI engineering",
  description:
    "Self-hosted data conversion for Data Engineering and AI Engineering. Turn documents, images and recordings into pipeline inputs. Direct Data Lake delivery is next.",
};
export default function Home() {
  return <LandingPage />;
}
