import { afterEach, describe, expect, test, vi } from "vitest"
import { checkRateLimit, peekRateLimit, clientIp } from "@/lib/rate-limit"

// checkRateLimit and peekRateLimit share one module-level `hits` map, so this
// exercises their interaction (not just one function in isolation) - each
// test uses its own key since the map isn't reset between tests.
describe("checkRateLimit + peekRateLimit", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  test("allows up to max hits, then rejects the next one within the window", () => {
    const key = "otp:test-under-over"
    expect(checkRateLimit(key, 3, 60_000).allowed).toBe(true)
    expect(checkRateLimit(key, 3, 60_000).allowed).toBe(true)
    expect(checkRateLimit(key, 3, 60_000).allowed).toBe(true)
    const fourth = checkRateLimit(key, 3, 60_000)
    expect(fourth.allowed).toBe(false)
    expect(fourth.retryAfterMs).toBeGreaterThan(0)
  })

  test("peekRateLimit reflects checkRateLimit's recorded hits without adding its own", () => {
    const key = "login:test-peek"
    expect(peekRateLimit(key, 2, 60_000)).toBe(false)
    checkRateLimit(key, 2, 60_000)
    checkRateLimit(key, 2, 60_000)
    expect(peekRateLimit(key, 2, 60_000)).toBe(true)
    // Calling peek again does not itself push the count past the cap.
    expect(peekRateLimit(key, 2, 60_000)).toBe(true)
  })

  test("a hit outside the window expires, freeing up a slot", () => {
    vi.useFakeTimers()
    const key = "otp:test-window-expiry"
    vi.setSystemTime(0)
    checkRateLimit(key, 1, 1_000)
    expect(checkRateLimit(key, 1, 1_000).allowed).toBe(false)

    vi.setSystemTime(1_500)
    expect(checkRateLimit(key, 1, 1_000).allowed).toBe(true)
  })
})

describe("clientIp", () => {
  test("prefers the first hop of x-forwarded-for", () => {
    const req = new Request("https://example.com", {
      headers: { "x-forwarded-for": "1.2.3.4, 5.6.7.8" },
    })
    expect(clientIp(req)).toBe("1.2.3.4")
  })

  test("falls back to x-real-ip when x-forwarded-for is absent", () => {
    const req = new Request("https://example.com", { headers: { "x-real-ip": "9.9.9.9" } })
    expect(clientIp(req)).toBe("9.9.9.9")
  })

  test("falls back to \"unknown\" with neither header", () => {
    const req = new Request("https://example.com")
    expect(clientIp(req)).toBe("unknown")
  })
})
