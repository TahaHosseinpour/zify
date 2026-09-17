-- Conversation lifecycle (bounded lifetime, resumable history) and per-EndUser
-- usage quotas. See packages/db/src/conversations.ts and
-- apps/agent/app/server.py for how these are used.

-- AlterTable
ALTER TABLE "conversations" ADD COLUMN "lastMessageAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- AlterTable
ALTER TABLE "end_users"
  ADD COLUMN "activeConversationId" TEXT,
  ADD COLUMN "webVisitorId" TEXT,
  ADD COLUMN "weeklyInputTokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "weeklyResetAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN "monthlyInputTokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "monthlyResetAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ALTER COLUMN "telegramUserId" DROP NOT NULL;

-- CreateIndex
CREATE UNIQUE INDEX "end_users_shopId_webVisitorId_key" ON "end_users"("shopId", "webVisitorId");

-- AlterTable
ALTER TABLE "shops"
  ADD COLUMN "monthlyProductUploads" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "monthlyUploadsResetAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- AlterTable
-- Pre-existing drift: password-login (see prisma/schema.prisma's User.password)
-- shipped to production already but this column was never pushed to local dev.
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "password" TEXT;
