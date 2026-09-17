import { prisma } from "@zify/db";

// Hard ceiling on how many *active* products a shop can have at once (each
// one is a standing OpenAI embedding, kept forever until deleted).
export const MAX_ACTIVE_PRODUCTS = 1000;

// Separate rolling-month cap on product *creates* - deleting and recreating
// products would otherwise be a free way around the active-product ceiling
// above while still paying for an embedding call every time. Lazy reset (like
// apps/agent/app/usage.py's token counters): checked/rolled-forward here on
// every create attempt, no cron needed.
export const MAX_MONTHLY_PRODUCT_UPLOADS = 2000;
const MONTH_MS = 30 * 24 * 60 * 60 * 1000;

export type ProductLimitCheck =
  | { ok: true }
  | { ok: false; reason: "active_cap" | "monthly_cap" };

/**
 * Call before `prisma.product.create`. On success, also records the create
 * against the monthly cap (that's the only side effect here - the active-cap
 * check is a pure read, since deletes/creates elsewhere already keep the
 * active count accurate).
 */
export async function checkAndRecordProductUpload(shopId: string): Promise<ProductLimitCheck> {
  const activeCount = await prisma.product.count({ where: { shopId, isActive: true } });
  if (activeCount >= MAX_ACTIVE_PRODUCTS) {
    return { ok: false, reason: "active_cap" };
  }

  const shop = await prisma.shop.findUniqueOrThrow({ where: { id: shopId } });
  const now = new Date();
  const expired = now.getTime() >= shop.monthlyUploadsResetAt.getTime();
  const currentCount = expired ? 0 : shop.monthlyProductUploads;

  if (currentCount >= MAX_MONTHLY_PRODUCT_UPLOADS) {
    return { ok: false, reason: "monthly_cap" };
  }

  await prisma.shop.update({
    where: { id: shopId },
    data: {
      monthlyProductUploads: currentCount + 1,
      monthlyUploadsResetAt: expired ? new Date(now.getTime() + MONTH_MS) : shop.monthlyUploadsResetAt,
    },
  });
  return { ok: true };
}
