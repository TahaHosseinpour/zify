// Pricing arithmetic, free of any database import so the pricing page can run
// it in the browser and show the same number the server will quote.
//
// Everything is derived from one measured figure: the most a single
// conversation can cost in model spend once every limit in
// packages/db/src/billing.ts is enforced. A plan's price is that ceiling,
// times the conversations it includes, times the markup - so a shop that uses
// every conversation it bought, each one to its limit, still costs less than
// it paid.

/** Hard ceiling on the model spend of one conversation, in toman. Enforced,
 * not estimated: a conversation is closed before it can cross it. */
export const CONVERSATION_COST_CAP_TOMAN = 3_000;

export const PRICE_MARKUP = 1.2;

/** What one conversation sells for on the custom plan. */
export const CUSTOM_PRICE_PER_CONVERSATION_TOMAN = Math.round(
  CONVERSATION_COST_CAP_TOMAN * PRICE_MARKUP,
);

export const PLAN_DURATIONS_MONTHS = [1, 3, 12] as const;
export type PlanDuration = (typeof PLAN_DURATIONS_MONTHS)[number];

export const CUSTOM_PLAN_KEY = "custom";
export const CUSTOM_MIN_CONVERSATIONS = 100;
export const CUSTOM_MAX_CONVERSATIONS = 100_000;
export const CUSTOM_CONVERSATION_STEP = 100;

/** The pricing fields of a Plan row - a structural type, so both the Prisma
 * model and a plain JSON copy of it sent to the browser satisfy it. */
export interface PlanPricing {
  monthlyPriceToman: number;
  discountPercent3Months: number;
  discountPercent12Months: number;
}

export function isPlanDuration(months: unknown): months is PlanDuration {
  return PLAN_DURATIONS_MONTHS.includes(months as PlanDuration);
}

function discountPercent(plan: PlanPricing, months: PlanDuration): number {
  if (months === 3) return plan.discountPercent3Months;
  if (months === 12) return plan.discountPercent12Months;
  return 0;
}

/** Total price of `months` of a plan, in toman. */
export function planPrice(plan: PlanPricing, months: PlanDuration): number {
  const full = plan.monthlyPriceToman * months;
  return Math.round((full * (100 - discountPercent(plan, months))) / 100);
}

export function clampCustomConversations(conversations: number): number {
  const stepped =
    Math.round(conversations / CUSTOM_CONVERSATION_STEP) * CUSTOM_CONVERSATION_STEP;
  return Math.min(CUSTOM_MAX_CONVERSATIONS, Math.max(CUSTOM_MIN_CONVERSATIONS, stepped));
}

/** Total price of `months` of a custom plan with this many conversations a
 * month. No duration discount: the per-conversation rate is already the floor. */
export function customPlanPrice(conversationsPerMonth: number, months: PlanDuration): number {
  return (
    clampCustomConversations(conversationsPerMonth) * CUSTOM_PRICE_PER_CONVERSATION_TOMAN * months
  );
}

/** The most a shop on this quota can cost in a month. */
export function maxMonthlyCostToman(conversationsPerMonth: number): number {
  return conversationsPerMonth * CONVERSATION_COST_CAP_TOMAN;
}
