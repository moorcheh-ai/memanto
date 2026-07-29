import { defineConfig } from "tsup";

export default defineConfig({
  entry: [
    "src/index.ts",
    "src/integrations/ai-sdk.ts",
    "src/integrations/openai.ts",
    "src/integrations/mastra.ts",
    "src/integrations/voltagent.ts",
  ],
  format: ["cjs", "esm"],
  dts: true,
  sourcemap: true,
  clean: true,
  splitting: false,
  target: "node18",
  outDir: "dist",
});
