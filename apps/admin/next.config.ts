import fs from "node:fs"
import path from "node:path"
import type { NextConfig } from "next"

const repoRoot = path.join(__dirname, "..", "..")

// Next only reads .env files from this app's directory, but the monorepo keeps a
// single root .env (see .env.example) that the bot and agent also read. Load it
// here so DATABASE_URL and friends reach the server runtime. Existing vars win,
// so a real environment (pm2, CI, shell) still overrides the file.
function loadRootEnv() {
  const envPath = path.join(repoRoot, ".env")
  let raw: string
  try {
    raw = fs.readFileSync(envPath, "utf8")
  } catch {
    return // no root .env (e.g. CI injects real env vars) — nothing to do
  }

  for (const line of raw.split(/\r?\n/)) {
    const match = /^\s*(?:export\s+)?([\w.-]+)\s*=\s*(.*)$/.exec(line)
    if (!match) continue

    const [, key] = match
    if (key in process.env) continue

    let value = match[2].trim()
    // Strip one layer of matching quotes; leave unquoted values as-is.
    if (value.length >= 2 && (value[0] === '"' || value[0] === "'") && value.at(-1) === value[0]) {
      value = value.slice(1, -1)
    } else {
      value = value.replace(/\s+#.*$/, "").trim()
    }
    process.env[key] = value
  }
}

loadRootEnv()

const nextConfig: NextConfig = {
  turbopack: {
    root: repoRoot,
  },
}

export default nextConfig
