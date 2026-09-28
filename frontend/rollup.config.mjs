import json from "@rollup/plugin-json";
import resolve from "@rollup/plugin-node-resolve";
import replace from "@rollup/plugin-replace";
import terser from "@rollup/plugin-terser";
import typescript from "@rollup/plugin-typescript";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));
const debug = Boolean(process.env.DEBUG);

const plugins = () => [
  replace({
    preventAssignment: true,
    values: {
      __VERSION__: JSON.stringify(pkg.version),
      __DEBUG__: JSON.stringify(debug),
    },
  }),
  resolve({ browser: true }),
  json(),
  typescript({ tsconfig: "./tsconfig.json", include: ["src/**/*"], noEmitOnError: true }),
  ...(debug ? [] : [terser({ format: { comments: false } })]),
];

// Two independent, self-contained bundles: the panel (hashed by scripts/stamp.mjs)
// and the card (stable filename, hashed only in the query string).
export default [
  {
    input: "src/panel-entry.ts",
    output: { file: "dist/entrypoint.js", format: "es", inlineDynamicImports: true },
    plugins: plugins(),
  },
  {
    input: "src/card-entry.ts",
    output: { file: "dist/anycubic-card.js", format: "es", inlineDynamicImports: true },
    plugins: plugins(),
  },
];
