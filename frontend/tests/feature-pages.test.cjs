const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Public feature pages: every docs link must resolve to a real topic, and the
// routes must be reachable from the header and listed in the sitemap.
function load(file, modules = {}) {
  const source = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const scope = { exports: {}, require: (name) => modules[name] };
  scope.module = { exports: scope.exports };
  vm.runInNewContext(compiled, scope);
  return scope.exports;
}

const { DOCS_TOPICS } = load("app/docs/topics.ts");
const { FEATURES, featureBySlug } = load("app/features/content.ts");
const slugs = new Set(DOCS_TOPICS.map((topic) => topic.slug));

assert.equal(FEATURES.map((feature) => feature.slug).join(), "documents,audio-video,images");
for (const feature of FEATURES) {
  assert.equal(featureBySlug(feature.slug), feature);
  assert.ok(feature.docs.length > 0, feature.slug);
  for (const { slug } of feature.docs) assert.ok(slugs.has(slug), `${feature.slug}: ${slug}`);
  assert.ok(feature.example.code.includes("$API/"), feature.slug);
  assert.ok(feature.example.code.includes("X-API-Key: $INGESTIFY_API_KEY"), feature.slug);
  for (const endpoint of feature.endpoints) assert.match(endpoint.path, /^\//);
  assert.ok(fs.existsSync(path.join(__dirname, `../app/features/${feature.slug}/page.tsx`)));
  // Product copy, metadata and examples describe capabilities independently of
  // the implementation chosen for an installation.
  assert.doesNotMatch(JSON.stringify(feature), /docling|florence|whisper|mediapipe|emotiefflib|\bmodal\b/i);
  assert.ok(feature.figure.operation, feature.slug);
}

// The Images table mirrors the Florence task catalog served by GET /images/capabilities.
const catalog = fs.readFileSync(
  path.join(__dirname, "../../backend/shared/vision_capabilities.py"),
  "utf8",
);
const backendTasks = [...catalog.matchAll(/^\s+"(<[A-Z_]+>)": \(/gm)].map((m) => m[1]);
const pageTasks = featureBySlug("images")
  .sections.find((section) => section.id === "tasks")
  .table.rows.map((row) => row[0]);
assert.equal(backendTasks.length, 15);
assert.equal([...pageTasks].sort().join(), [...backendTasks].sort().join());

const header = fs.readFileSync(path.join(__dirname, "../components/public-header.tsx"), "utf8");
assert.match(header, /href: "\/features", label: "Features"/);
const sitemap = fs.readFileSync(path.join(__dirname, "../app/sitemap.ts"), "utf8");
assert.match(sitemap, /\/features`/);
assert.match(sitemap, /FEATURES\.map/);

console.log("feature pages: content, docs links, header and sitemap ok");
