// In-memory sliding-window rate limiter. Safe because every service in this
// deploy runs as a single pm2 "fork" instance (see ecosystem.config.cjs) -
// no clustering, so there's exactly one process holding this Map and no risk
// of one replica letting through what another already capped. If that ever
// changes (multiple instances/clustering), this needs to move to a shared
// store (Redis) instead.

const hits = new Map<string, number[]>();

// Cheap, unbounded-growth guard: entries are pruned lazily on their own
// check, but a key that's never checked again (e.g. a one-off bad actor)
// would otherwise sit in the map forever. A full sweep every so often keeps
// memory bounded without needing a scheduled job.
let lastSweep = Date.now();
const SWEEP_INTERVAL_MS = 10 * 60 * 1000;

function sweep(now: number) {
  if (now - lastSweep < SWEEP_INTERVAL_MS) return;
  lastSweep = now;
  for (const [key, timestamps] of hits) {
    if (timestamps.length === 0 || now - timestamps[timestamps.length - 1] > SWEEP_INTERVAL_MS) {
      hits.delete(key);
    }
  }
}

/**
 * Records one hit for `key` and reports whether it exceeds `max` hits within
 * `windowMs`. Call once per attempt (e.g. once per OTP send, once per failed
 * login) - `allowed: false` means the caller should reject the request.
 */
export function checkRateLimit(
  key: string,
  max: number,
  windowMs: number,
): { allowed: boolean; retryAfterMs: number } {
  const now = Date.now();
  sweep(now);

  const timestamps = (hits.get(key) ?? []).filter((t) => now - t < windowMs);
  timestamps.push(now);
  hits.set(key, timestamps);

  if (timestamps.length > max) {
    const retryAfterMs = windowMs - (now - timestamps[0]);
    return { allowed: false, retryAfterMs: Math.max(retryAfterMs, 0) };
  }
  return { allowed: true, retryAfterMs: 0 };
}

/**
 * Read-only version of checkRateLimit - reports whether `key` is already at
 * or over `max` hits within `windowMs`, without recording a new hit. For
 * gates like "failed login attempts" where only failures should count: check
 * with `peekRateLimit` before the attempt, then `checkRateLimit` only if it
 * actually failed.
 */
export function peekRateLimit(key: string, max: number, windowMs: number): boolean {
  const now = Date.now();
  const timestamps = (hits.get(key) ?? []).filter((t) => now - t < windowMs);
  return timestamps.length >= max;
}

/** The client IP nginx forwards (see deploy/templates/zify.conf.j2's
 * proxy_set_header X-Real-IP/X-Forwarded-For) - falls back to "unknown"
 * locally where there's no proxy in front. */
export function clientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return request.headers.get("x-real-ip") ?? "unknown";
}
