-- Commercial layer: plans, hand-activated subscriptions, pricing-page leads,
-- per-conversation metering and a per-turn cost ledger. See
-- packages/db/src/billing.ts for how these are used.

-- CreateTable
-- Platform admins: their own entity, not a kind of user.
CREATE TABLE "admins" (
    "id" TEXT NOT NULL,
    "username" TEXT NOT NULL,
    "password" TEXT NOT NULL,
    "mobile" TEXT NOT NULL,
    "otpHash" TEXT,
    "otpExpiry" TIMESTAMP(3),
    "fullName" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "lastLoginAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "admins_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "admins_username_key" ON "admins"("username");

-- AlterTable
ALTER TABLE "end_users"
  ADD COLUMN "lastMessageAt" TIMESTAMP(3),
  ADD COLUMN "isBlocked" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "conversations"
  ADD COLUMN "userMessageCount" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "costToman" DECIMAL(12,2) NOT NULL DEFAULT 0,
  ADD COLUMN "billedAt" TIMESTAMP(3);

-- Conversations that already exist were real ones: count them from when they
-- started, with however many customer messages they hold.
UPDATE "conversations" c
SET "userMessageCount" = m.n, "billedAt" = c."startedAt"
FROM (
  SELECT "conversationId", count(*)::int AS n FROM "messages" WHERE role = 'user' GROUP BY 1
) m
WHERE m."conversationId" = c.id;

-- CreateIndex
CREATE INDEX "conversations_shopId_billedAt_idx" ON "conversations"("shopId", "billedAt");

-- CreateIndex
CREATE INDEX "conversations_endUserId_billedAt_idx" ON "conversations"("endUserId", "billedAt");

-- CreateTable
CREATE TABLE "plans" (
    "id" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "conversationsPerMonth" INTEGER NOT NULL,
    "monthlyPriceToman" INTEGER NOT NULL,
    "discountPercent3Months" INTEGER NOT NULL DEFAULT 0,
    "discountPercent12Months" INTEGER NOT NULL DEFAULT 0,
    "maxActiveProducts" INTEGER NOT NULL,
    "maxMonthlyProductUploads" INTEGER NOT NULL,
    "maxFaqItems" INTEGER NOT NULL,
    "maxBroadcastsPerMonth" INTEGER NOT NULL,
    "sortOrder" INTEGER NOT NULL DEFAULT 0,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "plans_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "plans_key_key" ON "plans"("key");

-- CreateTable
CREATE TABLE "subscriptions" (
    "id" TEXT NOT NULL,
    "shopId" TEXT NOT NULL,
    "planKey" TEXT NOT NULL,
    "planName" TEXT NOT NULL,
    "months" INTEGER NOT NULL,
    "startsAt" TIMESTAMP(3) NOT NULL,
    "endsAt" TIMESTAMP(3) NOT NULL,
    "conversationsPerMonth" INTEGER NOT NULL,
    "maxActiveProducts" INTEGER NOT NULL,
    "maxMonthlyProductUploads" INTEGER NOT NULL,
    "maxFaqItems" INTEGER NOT NULL,
    "maxBroadcastsPerMonth" INTEGER NOT NULL,
    "priceToman" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "note" TEXT,
    "activatedById" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "subscriptions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "subscriptions_shopId_status_endsAt_idx" ON "subscriptions"("shopId", "status", "endsAt");

-- AddForeignKey
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_shopId_fkey" FOREIGN KEY ("shopId") REFERENCES "shops"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- CreateTable
CREATE TABLE "leads" (
    "id" TEXT NOT NULL,
    "fullName" TEXT NOT NULL,
    "mobile" TEXT NOT NULL,
    "shopName" TEXT NOT NULL,
    "shopUrl" TEXT,
    "planKey" TEXT NOT NULL,
    "months" INTEGER NOT NULL,
    "conversationsPerMonth" INTEGER NOT NULL,
    "quotedPriceToman" INTEGER NOT NULL,
    "message" TEXT,
    "status" TEXT NOT NULL DEFAULT 'new',
    "adminNote" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "leads_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "leads_status_createdAt_idx" ON "leads"("status", "createdAt");

-- CreateTable
CREATE TABLE "usage_records" (
    "id" TEXT NOT NULL,
    "shopId" TEXT NOT NULL,
    "conversationId" TEXT,
    "inputTokens" INTEGER NOT NULL DEFAULT 0,
    "outputTokens" INTEGER NOT NULL DEFAULT 0,
    "jevTokens" INTEGER NOT NULL DEFAULT 0,
    "embeddingTokens" INTEGER NOT NULL DEFAULT 0,
    "costToman" DECIMAL(12,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "usage_records_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "usage_records_shopId_createdAt_idx" ON "usage_records"("shopId", "createdAt");

-- CreateIndex
CREATE INDEX "usage_records_conversationId_idx" ON "usage_records"("conversationId");

-- AddForeignKey
ALTER TABLE "usage_records" ADD CONSTRAINT "usage_records_shopId_fkey" FOREIGN KEY ("shopId") REFERENCES "shops"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- CreateTable
CREATE TABLE "settings" (
    "key" TEXT NOT NULL,
    "value" TEXT NOT NULL,

    CONSTRAINT "settings_pkey" PRIMARY KEY ("key")
);

-- The two plans on sale. Price = conversations x 3,000 toman (the hard cap on
-- what one conversation can cost, see billing.ts) x 1.2.
INSERT INTO "plans" ("id", "key", "name", "description", "conversationsPerMonth", "monthlyPriceToman",
                     "maxActiveProducts", "maxMonthlyProductUploads", "maxFaqItems", "maxBroadcastsPerMonth", "sortOrder")
VALUES
  ('plan_small', 'small', 'کسب‌وکار کوچک', 'برای فروشگاه‌هایی با چند ده مشتری در روز', 500, 1800000, 300, 300, 50, 2, 1),
  ('plan_large', 'large', 'کسب‌وکار بزرگ', 'برای فروشگاه‌های پرترافیک', 5000, 18000000, 3000, 3000, 300, 10, 2);

INSERT INTO "settings" ("key", "value") VALUES ('usd_toman', '300000');
