import { FeaturePage, featureMetadata } from "../feature-page";
import { featureBySlug } from "../content";

const feature = featureBySlug("images");

export const dynamic = "error";
export const metadata = featureMetadata(feature);

export default function ImagesFeaturePage() {
  return <FeaturePage feature={feature} />;
}
