import type { ParameterSchema } from "./api";

export interface LiveOptions {
  decoding?: Record<string, unknown>;
  interval_seconds?: number;
  max_context_seconds?: number;
  segment_no_speech_threshold?: number;
}

export interface LiveCapabilities {
  enabled: boolean;
  ready: boolean;
  options_supported: boolean;
  provider: string;
  model: string;
  languages: string[];
  protocol: number;
  max_duration_seconds: number;
  options_schema: ParameterSchema;
  managed_parameters: Record<string, unknown>;
  restrictions: string[];
}
