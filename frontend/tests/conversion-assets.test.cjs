const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const zlib = require("node:zlib");
const ts = require("typescript");

// lib/conversion-assets.ts: labels of the job page's Images tab and the
// store-only ZIP behind "Download all (.zip)".
const source = fs.readFileSync(path.join(__dirname, "../lib/conversion-assets.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const scope = { exports: {}, TextEncoder, Uint8Array, Uint32Array, DataView };
vm.runInNewContext(compiled, scope);
const { assetLabel, countAssetKinds, crc32, storeZip } = scope.exports;

assert.equal(assetLabel({ kind: "picture", page: 3, width: 1, height: 1 }), "Page 3 · picture");
assert.equal(assetLabel({ kind: "page", page: 12, width: 1, height: 1 }), "Page 12 · full page");
assert.equal(assetLabel({ kind: "picture", page: null, width: 1, height: 1 }), "Picture");
assert.deepEqual(
  { ...countAssetKinds([{ kind: "page" }, { kind: "picture" }, { kind: "picture" }]) },
  { pictures: 2, pages: 1 },
);

const encoder = new TextEncoder();
assert.equal(crc32(encoder.encode("123456789")), 0xcbf43926);
if (zlib.crc32) assert.equal(crc32(encoder.encode("hello")), zlib.crc32("hello"));

// The archive: local headers + data, central directory, end record; stored entries
const files = [
  { name: "p0001-page-aaaa.png", data: new Uint8Array([137, 80, 78, 71, 1, 2, 3]) },
  { name: "p0001-img01-bbbb.png", data: new Uint8Array([137, 80, 78, 71, 9]) },
];
const zip = Buffer.from(storeZip(files));
assert.equal(zip.readUInt32LE(0), 0x04034b50);
const end = zip.length - 22;
assert.equal(zip.readUInt32LE(end), 0x06054b50);
assert.equal(zip.readUInt16LE(end + 10), 2);
const centralSize = zip.readUInt32LE(end + 12);
const centralOffset = zip.readUInt32LE(end + 16);
assert.equal(centralOffset + centralSize, end);

let at = centralOffset;
for (const file of files) {
  assert.equal(zip.readUInt32LE(at), 0x02014b50);
  const nameLength = zip.readUInt16LE(at + 28);
  const local = zip.readUInt32LE(at + 42);
  assert.equal(zip.toString("utf8", at + 46, at + 46 + nameLength), file.name);
  // Its local entry: same name, stored (method 0), sizes and CRC, then the bytes as-is
  assert.equal(zip.readUInt32LE(local), 0x04034b50);
  assert.equal(zip.readUInt16LE(local + 8), 0);
  assert.equal(zip.readUInt32LE(local + 14), crc32(file.data));
  assert.equal(zip.readUInt32LE(local + 18), file.data.length);
  const dataStart = local + 30 + zip.readUInt16LE(local + 26);
  assert.deepEqual([...zip.subarray(dataStart, dataStart + file.data.length)], [...file.data]);
  at += 46 + nameLength;
}

console.log("Conversion assets: labels, CRC-32 and the stored ZIP passed.");
