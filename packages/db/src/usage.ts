import { prisma } from "./index";

// Input-token caps per EndUser (per customer, not per shop - a shop with many
// customers isn't penalised for one of them chatting a lot; that one customer
// is). Mirrored in apps/agent/app/usage.py, which is where these are actually
// enforced (this TS side is display-only: admin panel + the bot's usage
// button) - keep both in sync if these ever change.
export const WEEKLY_INPUT_TOKEN_LIMIT = 80_000;
export const MONTHLY_INPUT_TOKEN_LIMIT = 200_000;

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const MONTH_MS = 30 * 24 * 60 * 60 * 1000;

export interface UsageStatus {
  weeklyUsed: number;
  weeklyLimit: number;
  weeklyResetAt: Date;
  monthlyUsed: number;
  monthlyLimit: number;
  monthlyResetAt: Date;
  overLimit: boolean;
}

function lazyReset(now: number, resetAt: Date, windowMs: number, used: number) {
  if (now >= resetAt.getTime()) {
    return { used: 0, resetAt: new Date(now + windowMs) };
  }
  return { used, resetAt };
}

/**
 * Current usage, rolling forward any window that has already expired - purely
 * a read, so an expired window shows as reset (0 used, a fresh reset date)
 * without writing anything. apps/agent/app/usage.py's `increment_input_tokens`
 * is what actually persists a roll-forward, the next time this end user
 * chats; a shop owner just looking at the dashboard should never be the thing
 * that "uses" the roll-forward.
 */
export async function getUsageStatus(endUserId: string): Promise<UsageStatus> {
  const endUser = await prisma.endUser.findUniqueOrThrow({ where: { id: endUserId } });
  const now = Date.now();
  const weekly = lazyReset(now, endUser.weeklyResetAt, WEEK_MS, endUser.weeklyInputTokens);
  const monthly = lazyReset(now, endUser.monthlyResetAt, MONTH_MS, endUser.monthlyInputTokens);
  return {
    weeklyUsed: weekly.used,
    weeklyLimit: WEEKLY_INPUT_TOKEN_LIMIT,
    weeklyResetAt: weekly.resetAt,
    monthlyUsed: monthly.used,
    monthlyLimit: MONTHLY_INPUT_TOKEN_LIMIT,
    monthlyResetAt: monthly.resetAt,
    overLimit: weekly.used >= WEEKLY_INPUT_TOKEN_LIMIT || monthly.used >= MONTHLY_INPUT_TOKEN_LIMIT,
  };
}
