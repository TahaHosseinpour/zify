// How this app talks to the agent service (apps/agent).

export const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:3001"

/** Headers for every request to the agent. The agent rejects callers without
 * the shared key whenever one is configured (see apps/agent/app/server.py) -
 * it runs every model call the platform pays for, so nothing but our own
 * services may reach it. */
export function agentHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const key = process.env.AGENT_INTERNAL_KEY
  if (key) headers["x-agent-key"] = key
  return headers
}
