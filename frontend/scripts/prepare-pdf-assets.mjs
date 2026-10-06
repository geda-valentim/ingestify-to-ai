import { cp, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const pdfjs = dirname(require.resolve("pdfjs-dist/package.json"));
const destination = fileURLToPath(new URL("../public/pdfjs/", import.meta.url));
await mkdir(destination, { recursive: true });
// Worker and these decoder/font assets must come from the same locked version.
for (const directory of ["wasm", "cmaps", "standard_fonts"]) {
  await cp(join(pdfjs, directory), join(destination, directory), { recursive: true });
}
