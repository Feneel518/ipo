import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // Bklit registry components are vendored upstream source and use Biome directives.
  globalIgnores([".next/**", "next-env.d.ts", "src/components/charts/**"]),
]);
