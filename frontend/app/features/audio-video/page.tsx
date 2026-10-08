import { FeaturePage, featureMetadata } from "../feature-page";
import { featureBySlug } from "../content";

const feature = featureBySlug("audio-video");

export const dynamic = "error";
export const metadata = featureMetadata(feature);

export default function AudioVideoFeaturePage() {
  return <FeaturePage feature={feature} />;
}
