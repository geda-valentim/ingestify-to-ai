import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";
export const metadata: Metadata = {
  title: "Ingestify — Seus arquivos, prontos para IA",
  description:
    "Transforme documentos, imagens, áudio e vídeo em informação para suas aplicações. Explore as operações, a API e o controle sobre a execução do Ingestify.",
};
export default function Home() {
  return <LandingPage />;
}
