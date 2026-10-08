// Server-Sent Events framing shared by the storefront chat: `event: <type>
// \ndata: <json>\n\n` blocks, matching what apps/agent/app/server.py's
// /chat/stream writes.

export interface SseEvent<T = unknown> {
  event: string
  data: T
}

/** A complete, already-finished stream carrying one assistant message - for
 * replies that never involve the agent (a refusal, a rate limit). The chat UI
 * reads it exactly like a real turn, so the text shows up as the assistant's
 * answer rather than as a transport error. */
export function sseTextResponse(text: string, headers: Record<string, string> = {}): Response {
  const body =
    `event: answer\ndata: ${JSON.stringify({ text })}\n\n` +
    `event: done\ndata: ${JSON.stringify({ products: [], showBuyActions: false })}\n\n`
  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      ...headers,
    },
  })
}

/** Parse a *complete* SSE payload (already-buffered text) into events. Used
 * server-side in api/shop-chat/route.ts to reconstruct the full reply for
 * persistence from the tapped copy of the stream. */
export function parseSseEvents(text: string): SseEvent[] {
  const events: SseEvent[] = []
  for (const block of text.split("\n\n")) {
    if (!block.trim()) continue
    let event: string | undefined
    let data: unknown
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice("event: ".length)
      else if (line.startsWith("data: ")) {
        try {
          data = JSON.parse(line.slice("data: ".length))
        } catch {
          // malformed chunk - skip rather than crash persistence
        }
      }
    }
    if (event) events.push({ event, data })
  }
  return events
}

/**
 * Incrementally parse SSE text as it arrives over a fetch ReadableStream -
 * used client-side, where events must be handled as soon as each one is
 * complete rather than waiting for the whole response. Call `push` with each
 * decoded chunk; it returns any newly-completed events and keeps a partial
 * trailing block buffered internally for the next call.
 */
export function createSseStreamParser() {
  let buffer = ""
  return {
    push(chunk: string): SseEvent[] {
      buffer += chunk
      const blocks = buffer.split("\n\n")
      buffer = blocks.pop() ?? "" // last piece may be incomplete
      return blocks
        .filter((b) => b.trim())
        .map((block) => {
          let event: string | undefined
          let data: unknown
          for (const line of block.split("\n")) {
            if (line.startsWith("event: ")) event = line.slice("event: ".length)
            else if (line.startsWith("data: ")) {
              try {
                data = JSON.parse(line.slice("data: ".length))
              } catch {
                // ignore
              }
            }
          }
          return { event: event ?? "", data }
        })
        .filter((e) => e.event)
    },
  }
}
