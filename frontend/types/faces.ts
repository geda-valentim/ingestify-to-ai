import type { ImageFullAnalysisResult, ImageFullStepResult, ParameterSchema } from "./api";

export type FaceOperation = "face_detection" | "face_movements" | "face_expression_classification";
export interface FaceOptions {
  mode?: "detection" | "expressions";
  max_faces?: number;
  min_detection_confidence?: number;
  min_suppression_threshold?: number;
  min_face_presence_confidence?: number;
  min_expression_score?: number;
  deadline_seconds?: number;
}
export interface FaceStep {
  kind: "face"; step_id: string; operation: FaceOperation; face_id?: string | null;
  status: ImageFullStepResult["status"]; reason_code?: string | null;
  output?: Record<string, unknown>; duration_ms?: number; attempts?: number;
}
export interface FacialBlock {
  detection: { status: string; reason_code?: string | null; detected_count?: number; selected_count?: number; omitted_count?: number; selection_limited?: boolean };
  faces: {
    face_id: string; bbox: number[]; bbox_normalized: number[]; detection_confidence: number;
    keypoints: { x: number; y: number; index: number }[];
    movements: { status: string; reason_code?: string | null; landmarks?: { x: number; y: number; index: number }[]; blendshapes?: { name: string; score: number }[] };
    expression: { status: string; reason_code?: string | null; decision?: string; label?: string | null; score?: number; scores?: { label: string; score: number }[]; calibrated?: boolean; threshold?: number };
  }[];
  models: { provider: string; model_id: string; revision: string; sha256: string; runtime: string; runtime_version: string; license: string }[];
  request: FaceOptions;
  steps: FaceStep[];
  coverage: { task_families_total: number; task_families_completed: number; families: { task: FaceOperation; label: string; completed: boolean; reason_codes: string[] }[] };
}
export interface FaceAnalysisResult extends FacialBlock {
  operation: "face_analysis"; profile: "image-faces-v1"; schema_version: "face-result-v1";
  width: number; height: number; image_base64?: string | null; image_mime_type: string;
  analysis_status: ImageFullAnalysisResult["analysis_status"]; duration_ms: number;
  calls_started: number; calls_by_provider: Record<string, number>; reason_code?: string | null;
}
export interface ImageFullV2Result extends Omit<ImageFullAnalysisResult, "results" | "coverage"> {
  profile: "image-full-v2"; schema_version: "image-full-result-v2";
  faces: FacialBlock; models: Record<string, unknown>[];
  results: ((ImageFullStepResult & { kind: "florence" }) | FaceStep)[];
  coverage: Omit<ImageFullAnalysisResult["coverage"], "families"> & {
    families: (ImageFullAnalysisResult["coverage"]["families"][number] | FacialBlock["coverage"]["families"][number])[];
  };
}
export interface FaceCapabilities {
  enabled: boolean; ready: boolean; reason?: string | null;
  stages: Record<FaceOperation, { ready: boolean; reason?: string | null }>;
  options_schema: ParameterSchema; full_options_schema: ParameterSchema; defaults: FaceOptions;
  max_image_size_mb: number; models: FacialBlock["models"];
}
