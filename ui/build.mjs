import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

await mkdir("dist", { recursive: true });
await build({
  entryPoints: ["src/main.ts"],
  outfile: "dist/main.js",
  bundle: true,
  minify: true,
  target: "es2022",
  format: "iife",
});
await copyFile("src/index.html", "dist/index.html");
