const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Spec 0014 §4.10: each admin section needs its own permission from /auth/me.
const source = fs.readFileSync(path.join(__dirname, "../lib/admin-nav.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const scope = { exports: {} };
vm.runInNewContext(compiled, scope);
const { ADMIN_SECTION_PERMISSIONS, canOpenAdminSection, adminSectionsFor } = scope.exports;

// The vm realm has its own Array: copy before comparing.
const sections = (u) => [...adminSectionsFor(u)];
const viewer = (permissions, is_admin = false) => ({ is_admin, permissions });
const ALL = [...Object.keys(ADMIN_SECTION_PERMISSIONS)];

assert.deepEqual(sections(null), []);
assert.deepEqual(sections(viewer([], true)), ALL);

// platform_operator: Routing and Status, nothing else (GPUs stays admin only).
assert.deepEqual(
  sections(viewer(["platform.stats.read", "platform.routing.read", "platform.jobs.read"])),
  ["/admin/routing", "/admin/status"],
);
// platform_auditor: the bindings list and the read-only platform views.
assert.deepEqual(
  sections(viewer(["platform.routing.read", "iam.bindings.read", "platform.audit.read"])),
  ["/admin/platform-access", "/admin/routing", "/admin/status"],
);
// remote_engine_user only: no admin section at all.
assert.deepEqual(sections(viewer(["engines.remote.use"])), []);
// 0009 observer: engines and profiles.
assert.deepEqual(
  sections(viewer(["engines.read", "execution_profiles.read"])),
  ["/admin/engines", "/admin/execution-profiles"],
);
assert.equal(canOpenAdminSection(viewer(["engines.read"]), "/admin/gpus"), false);
assert.equal(canOpenAdminSection(viewer([], true), "/admin/gpus"), true);
assert.equal(canOpenAdminSection(viewer(["engines.read"]), "/admin/unknown"), false);

// Every permission named here exists in the backend (0014 catalog or 0009 access).
const backend = ["shared/iam/catalog.py", "shared/access/service.py", "shared/access/policy.py"]
  .map((f) => path.join(__dirname, "../../backend", f))
  .filter((f) => fs.existsSync(f))
  .map((f) => fs.readFileSync(f, "utf8"))
  .join("\n");
for (const needed of Object.values(ADMIN_SECTION_PERMISSIONS)) {
  if (needed !== null) assert.ok(backend.includes(`"${needed}"`), `unknown permission ${needed}`);
}

console.log("admin-nav: ok");
