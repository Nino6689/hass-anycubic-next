import { defineConfig } from "vitest/config";

export default defineConfig({
  define: { __VERSION__: JSON.stringify("test"), __DEBUG__: "false" },
  test: { include: ["tests/**/*.test.ts"], environment: "node" },
});
