import type { Constraints } from "./access";
/** Spec 0014 §4.9: platform roles granted through IAM bindings. */
export interface IamRole {
  key: string;
  /** Role family (spec 0018): `engines` are the 0009 roles, granted with a condition. */
  family: "platform" | "engines";
  permissions: string[];
  description: string;
}
export interface IamCatalog {
  permissions: {
    name: string;
    family: string;
    level: string;
    mutation: boolean;
  }[];
  roles: IamRole[];
  /** IAM_MODE: bindings only take effect under `enforce` (spec 0014 §4.11). */
  mode?: "off" | "shadow" | "enforce";
}
/** The 0009 delegation envelope of an `access_admin` engines binding. */
export interface IamDelegation {
  permissions: string[];
  constraints: Constraints;
  max_grant_seconds: number;
}
export interface IamBinding {
  id: string;
  /** Spec 0018: `engines` bindings carry the four fields below; `platform` ones never. */
  family: "platform" | "engines";
  subject_type: "user" | "service_principal";
  subject_id: string;
  role: string;
  scope_type: string;
  scope_id: string | null;
  /** Materialized permission subset of the role. */
  permissions: string[] | null;
  /** The condition: an access policy revision id. */
  condition_ref: string | null;
  delegation: IamDelegation | null;
  /** The delegate's `access_admin` binding that authorized this one. */
  parent_id: string | null;
  granted_by: string | null;
  /** Naive UTC ISO-8601. */
  expires_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  version: number;
  created_at: string | null;
  /** For an engines binding, also its parent chain and owner (the 0009 decision). */
  active: boolean;
}
export interface IamBindingCreate {
  subject_type: "user";
  subject_id: string;
  role: string;
  expires_at: string;
  /** Engines roles only (422 FIELD_NOT_ALLOWED_FOR_ROLE on a platform role). */
  permissions?: string[];
  condition_ref?: string;
  delegation?: IamDelegation;
}
