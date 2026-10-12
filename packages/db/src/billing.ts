import { prisma } from "./index";
import type { Conversation, Subscription } from "@prisma/client";
import { CONVERSATION_TTL_MS, createAndActivate } from "./conversations";

// ── The gate every customer message passes before it reaches the agent ───────
//
// A subscription sells conversations, and its price is built on one promise:
// no conversation can cost more than MAX_CONVERSATION_COST_TOMAN in model
// spend (see packages/shared/src/plans.ts). The limits below are what make
// that true. They also protect the shop owner from their own customers - one
// visitor, or one script, must never be able to drain a month of quota.
//
// The same function serves the storefront chat, the playground and the
// Telegram bot, so no channel can be the unguarded way in.

/** A conversation ends after this many customer messages; the next one starts
 * (and bills) a new conversation. */
export const MAX_MESSAGES_PER_CONVERSATION = 8;
/** Longest customer message the agent will be asked to read. */
export const MAX_MESSAGE_CHARS = 300;
/** Mirrors CONVERSATION_COST_CAP_TOMAN in @zify/shared - kept as its own
 * constant here so this package needs no dependency on that one. */
export const MAX_CONVERSATION_COST_TOMAN = 3_000;
/** The most one turn can cost with every per-turn limit at its maximum. A
 * conversation whose recorded spend is within this of the ceiling is closed
 * rather than allowed one more turn that could cross it.
 *
 * Measured at ~550 when replies came from a model at $0.15 / $0.60 per million
 * tokens. The model asked first now costs twice that and may write 400 tokens
 * instead of 300, so this is that figure doubled - an estimate, not yet
 * measured again. */
export const MAX_TURN_COST_TOMAN = 1_200;
/** Two messages closer together than this are a script, not a person. */
export const MIN_MESSAGE_INTERVAL_MS = 3_000;
/** New conversations one customer may start in 24 hours. */
export const MAX_CONVERSATIONS_PER_END_USER_PER_DAY = 3;
/** Share of the monthly quota a shop may spend in any 24 hours. Whatever an
 * attack looks like, it burns at most this much before the assistant pauses
 * for the day. */
export const SHOP_DAILY_QUOTA_SHARE = 0.1;
const SHOP_DAILY_QUOTA_FLOOR = 10;

const DAY_MS = 24 * 60 * 60 * 1000;
export const SUBSCRIPTION_MONTH_MS = 30 * DAY_MS;

export type TurnDenialReason =
  | "no_subscription"
  | "quota_exhausted"
  | "shop_daily_cap"
  | "end_user_daily_cap"
  | "message_too_long"
  | "too_fast"
  | "blocked";

// Shown to the *customer*. A shop's billing state is none of their business,
// so every reason that comes down to "this shop's assistant is off" reads the
// same.
const ASSISTANT_OFF =
  "دستیار این فروشگاه در حال حاضر فعال نیست. لطفاً بعداً دوباره سر بزنید یا مستقیم با فروشگاه در تماس باشید.";

export const TURN_DENIAL_MESSAGES: Record<TurnDenialReason, string> = {
  no_subscription: ASSISTANT_OFF,
  quota_exhausted: ASSISTANT_OFF,
  shop_daily_cap: ASSISTANT_OFF,
  blocked: ASSISTANT_OFF,
  end_user_daily_cap: "به سقف گفتگوی امروز رسیده‌اید. فردا دوباره در خدمتتان هستیم.",
  message_too_long: `پیام شما طولانی است. لطفاً آن را در حداکثر ${MAX_MESSAGE_CHARS.toLocaleString("fa-IR")} کاراکتر بنویسید.`,
  too_fast: "لطفاً چند لحظه صبر کنید و دوباره پیام بدهید.",
};

export type TurnAdmission =
  | { ok: true; conversation: Conversation; subscription: Subscription }
  | { ok: false; reason: TurnDenialReason; message: string };

function deny(reason: TurnDenialReason): TurnAdmission {
  return { ok: false, reason, message: TURN_DENIAL_MESSAGES[reason] };
}

/** The subscription that is in force for this shop right now, if any. */
export function getActiveSubscription(
  shopId: string,
  now: Date = new Date(),
): Promise<Subscription | null> {
  return prisma.subscription.findFirst({
    where: { shopId, status: "active", startsAt: { lte: now }, endsAt: { gt: now } },
    orderBy: { endsAt: "desc" },
  });
}

/** Start of the 30-day quota period `now` falls in. A 3- or 12-month
 * subscription is that many periods back to back, each with a fresh quota. */
export function quotaPeriodStart(subscription: Pick<Subscription, "startsAt">, now: Date): Date {
  const elapsed = Math.max(0, now.getTime() - subscription.startsAt.getTime());
  const periods = Math.floor(elapsed / SUBSCRIPTION_MONTH_MS);
  return new Date(subscription.startsAt.getTime() + periods * SUBSCRIPTION_MONTH_MS);
}

export function shopDailyConversationCap(conversationsPerMonth: number): number {
  return Math.max(
    SHOP_DAILY_QUOTA_FLOOR,
    Math.ceil(conversationsPerMonth * SHOP_DAILY_QUOTA_SHARE),
  );
}

export interface QuotaStatus {
  subscription: Subscription | null;
  conversationsUsed: number;
  conversationsLimit: number;
  periodStart: Date | null;
  periodEnd: Date | null;
  /** Real model spend recorded for this period's conversations, in toman. */
  costToman: number;
}

/** Where a shop stands in its current period - for the owner's dashboard and
 * the platform admin's shop list. */
export async function getQuotaStatus(shopId: string, now: Date = new Date()): Promise<QuotaStatus> {
  const subscription = await getActiveSubscription(shopId, now);
  if (!subscription) {
    return {
      subscription: null,
      conversationsUsed: 0,
      conversationsLimit: 0,
      periodStart: null,
      periodEnd: null,
      costToman: 0,
    };
  }

  const periodStart = quotaPeriodStart(subscription, now);
  const periodEnd = new Date(
    Math.min(periodStart.getTime() + SUBSCRIPTION_MONTH_MS, subscription.endsAt.getTime()),
  );
  const usage = await prisma.conversation.aggregate({
    where: { shopId, billedAt: { gte: periodStart } },
    _count: { _all: true },
    _sum: { costToman: true },
  });
  return {
    subscription,
    conversationsUsed: usage._count._all,
    conversationsLimit: subscription.conversationsPerMonth,
    periodStart,
    periodEnd,
    costToman: Number(usage._sum.costToman ?? 0),
  };
}

/** True when this conversation has no room for another turn: it is at its
 * message cap, or close enough to its cost ceiling that one more turn could
 * cross it. */
export function isConversationSpent(
  conversation: Pick<Conversation, "userMessageCount" | "costToman">,
): boolean {
  return (
    conversation.userMessageCount >= MAX_MESSAGES_PER_CONVERSATION ||
    Number(conversation.costToman) + MAX_TURN_COST_TOMAN > MAX_CONVERSATION_COST_TOMAN
  );
}

export interface AdmitTurnInput {
  shopId: string;
  endUserId: string;
  message: string;
  mode: string;
  productId?: string | null;
  /** The shop owner testing in the playground: still spends the shop's quota
   * (it costs the same), but is not subject to the per-customer abuse limits. */
  isOwner?: boolean;
  now?: Date;
}

/**
 * Decide whether this customer message may be answered, and by which
 * conversation. Call it once per incoming message, before the agent.
 *
 * On success the returned conversation has already been counted: its message
 * count is incremented, and if this was its first message it has been billed
 * against the shop's quota. On refusal nothing was spent and `message` is
 * ready to show the customer.
 */
export async function admitTurn(input: AdmitTurnInput): Promise<TurnAdmission> {
  const { shopId, endUserId, message, mode, productId, isOwner = false } = input;
  const now = input.now ?? new Date();

  if (message.length > MAX_MESSAGE_CHARS) return deny("message_too_long");

  const subscription = await getActiveSubscription(shopId, now);
  if (!subscription) return deny("no_subscription");

  const endUser = await prisma.endUser.findUnique({ where: { id: endUserId } });
  if (!endUser || endUser.shopId !== shopId) {
    throw new Error(`admitTurn: no EndUser ${endUserId} in shop ${shopId}`);
  }
  if (endUser.isBlocked) return deny("blocked");
  if (
    !isOwner &&
    endUser.lastMessageAt &&
    now.getTime() - endUser.lastMessageAt.getTime() < MIN_MESSAGE_INTERVAL_MS
  ) {
    return deny("too_fast");
  }

  // The conversation this message continues: the active one while it is
  // recent and still has room, otherwise a new one.
  let conversation: Conversation | null = null;
  if (endUser.activeConversationId) {
    const active = await prisma.conversation.findUnique({
      where: { id: endUser.activeConversationId },
    });
    if (
      active &&
      now.getTime() - active.lastMessageAt.getTime() < CONVERSATION_TTL_MS &&
      !isConversationSpent(active)
    ) {
      conversation = active;
    }
  }
  if (!conversation) {
    conversation = await createAndActivate(shopId, endUserId, mode, productId);
  }
  const conversationId = conversation.id;

  // Counting happens under a per-shop lock so two first messages arriving at
  // once cannot both take the last conversation in the quota.
  const outcome = await prisma.$transaction(async (tx) => {
    // $executeRaw, not $queryRaw: the function returns void, which Prisma
    // cannot read back as a result column.
    await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${shopId}))`;

    const current = await tx.conversation.findUniqueOrThrow({ where: { id: conversationId } });
    if (isConversationSpent(current)) return "retry" as const;

    if (current.billedAt === null) {
      // First message: this is the moment the conversation is sold.
      const periodStart = quotaPeriodStart(subscription, now);
      const usedThisPeriod = await tx.conversation.count({
        where: { shopId, billedAt: { gte: periodStart } },
      });
      if (usedThisPeriod >= subscription.conversationsPerMonth) return "quota_exhausted" as const;

      const dayAgo = new Date(now.getTime() - DAY_MS);
      const usedToday = await tx.conversation.count({
        where: { shopId, billedAt: { gte: dayAgo } },
      });
      if (usedToday >= shopDailyConversationCap(subscription.conversationsPerMonth)) {
        return "shop_daily_cap" as const;
      }

      if (!isOwner) {
        const startedByCustomerToday = await tx.conversation.count({
          where: { endUserId, billedAt: { gte: dayAgo } },
        });
        if (startedByCustomerToday >= MAX_CONVERSATIONS_PER_END_USER_PER_DAY) {
          return "end_user_daily_cap" as const;
        }
      }
    }

    return tx.conversation.update({
      where: { id: conversationId },
      data: {
        userMessageCount: { increment: 1 },
        lastMessageAt: now,
        billedAt: current.billedAt ?? now,
      },
    });
  });

  if (outcome === "retry") {
    // Another message filled this conversation between the read above and the
    // lock. Its successor is a fresh conversation, so one retry settles it.
    return admitTurn({ ...input, now });
  }
  if (typeof outcome === "string") return deny(outcome);

  await prisma.endUser.update({ where: { id: endUserId }, data: { lastMessageAt: now } });
  return { ok: true, conversation: outcome, subscription };
}

// ── Subscription limits outside the conversation path ────────────────────────

/** What a shop with no subscription may still do: build its catalog, so it is
 * ready to switch on the day it pays. Matches the small plan. */
export const NO_SUBSCRIPTION_LIMITS = {
  maxActiveProducts: 300,
  maxMonthlyProductUploads: 300,
  maxFaqItems: 50,
  maxBroadcastsPerMonth: 0,
} as const;

export type ShopLimits = {
  maxActiveProducts: number;
  maxMonthlyProductUploads: number;
  maxFaqItems: number;
  maxBroadcastsPerMonth: number;
};

export async function getShopLimits(shopId: string, now: Date = new Date()): Promise<ShopLimits> {
  const subscription = await getActiveSubscription(shopId, now);
  if (!subscription) return NO_SUBSCRIPTION_LIMITS;
  return {
    maxActiveProducts: subscription.maxActiveProducts,
    maxMonthlyProductUploads: subscription.maxMonthlyProductUploads,
    maxFaqItems: subscription.maxFaqItems,
    maxBroadcastsPerMonth: subscription.maxBroadcastsPerMonth,
  };
}
