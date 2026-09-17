import { defineConfig } from "vitest/config"
import path from "node:path"

// Tests live at the repo root (/tests), grouped by kind, not next to the
// app - see /tests/unit/admin and /tests/integration/admin.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: [
      "../../tests/unit/admin/**/*.test.{ts,tsx}",
      "../../tests/integration/admin/**/*.test.{ts,tsx}",
    ],
  },
})
