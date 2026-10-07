/** Spec 0014 §4.9: platform roles granted through IAM bindings. */
export interface IamRole {
  key: string;
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
}
export interface IamBinding {
  id: string;
  subject_type: "user" | "service_principal";
  subject_id: string;
  role: string;
  scope_type: string;
  scope_id: string | null;
  granted_by: string | null;
  /** Naive UTC ISO-8601. */
  expires_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  version: number;
  created_at: string | null;
  active: boolean;
}
export interface IamBindingCreate {
  subject_type: "user";
  subject_id: string;
  role: string;
  expires_at: string;
}
