import type { UserResponse } from "@/types/api";

/**
 * Admin sections and the permission each one needs (spec 0014 §4.10). The API
 * still authorizes every call; this only keeps the navigation honest, so a
 * user sees exactly the sections their `/auth/me` permissions open.
 *
 * `null` means "effective admin only": GPUs still sit behind `require_admin`
 * (0009 engine routes, unchanged by 0014).
 */
export const ADMIN_SECTION_PERMISSIONS: Record<string, string | null> = {
  "/admin/engines": "engines.read",
  "/admin/execution-profiles": "execution_profiles.read",
  "/admin/access": "access.grants.manage",
  "/admin/platform-access": "iam.bindings.read",
  "/admin/gpus": null,
  "/admin/routing": "platform.routing.read",
  "/admin/status": "platform.routing.read",
};

type Viewer = Pick<UserResponse, "is_admin" | "permissions"> | null | undefined;

export function canOpenAdminSection(user: Viewer, href: string): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  if (!(href in ADMIN_SECTION_PERMISSIONS)) return false;
  const needed = ADMIN_SECTION_PERMISSIONS[href];
  return needed !== null && !!user.permissions?.includes(needed);
}

/** Sections the viewer can open, in navigation order. */
export function adminSectionsFor(user: Viewer): string[] {
  return Object.keys(ADMIN_SECTION_PERMISSIONS).filter((href) =>
    canOpenAdminSection(user, href),
  );
}
