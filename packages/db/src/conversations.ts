import { prisma } from "./index";
import type { Conversation } from "@prisma/client";

// How long a conversation stays "the one your next message continues" before
// a new message starts a fresh one instead. This is also what fixes the
// agent's shop_categories/shop_brands cache going stale forever: the
// LangGraph thread id is keyed by conversation id (see callers), so a new
// conversation means a genuinely empty checkpoint - fresh vocabulary, fresh
// message history - not a resumed one.
export const CONVERSATION_TTL_MS = 24 * 60 * 60 * 1000;

export async function createAndActivate(
  shopId: string,
  endUserId: string,
  mode: string,
  productId?: string | null,
): Promise<Conversation> {
  const conversation = await prisma.conversation.create({
    data: { shopId, endUserId, mode, productId: productId ?? undefined },
  });
  await prisma.endUser.update({
    where: { id: endUserId },
    data: { activeConversationId: conversation.id },
  });
  return conversation;
}

/**
 * The conversation this end user's next message continues - the existing
 * active one if it's still within the 24h window, otherwise a brand new one.
 * Bumps `lastMessageAt` either way, since being asked for at all means a
 * message just arrived.
 */
export async function getOrStartConversation(
  shopId: string,
  endUserId: string,
  mode: string,
  productId?: string | null,
): Promise<Conversation> {
  const endUser = await prisma.endUser.findUnique({ where: { id: endUserId } });
  if (!endUser) {
    throw new Error(`getOrStartConversation: no EndUser with id ${endUserId}`);
  }

  if (endUser.activeConversationId) {
    const active = await prisma.conversation.findUnique({
      where: { id: endUser.activeConversationId },
    });
    if (active && Date.now() - active.lastMessageAt.getTime() < CONVERSATION_TTL_MS) {
      return prisma.conversation.update({
        where: { id: active.id },
        // Arriving from a product link points the running conversation at
        // that product. Without this the link only worked for a customer
        // with no conversation in the last 24h - anyone else kept talking
        // about whatever they had open before.
        data: { lastMessageAt: new Date(), ...(productId ? { mode, productId } : {}) },
      });
    }
  }

  return createAndActivate(shopId, endUserId, mode, productId);
}

/** Force a fresh conversation regardless of the 24h window - the explicit
 * "new chat" action. */
export function startNewConversation(
  shopId: string,
  endUserId: string,
  mode = "explore",
): Promise<Conversation> {
  return createAndActivate(shopId, endUserId, mode);
}

/** Make an old conversation (must belong to this shop+endUser) the active one
 * again, so the next message continues it instead of starting a new one. */
export async function resumeConversation(
  shopId: string,
  endUserId: string,
  conversationId: string,
): Promise<Conversation | null> {
  const conversation = await prisma.conversation.findFirst({
    where: { id: conversationId, shopId, endUserId },
  });
  if (!conversation) return null;

  await prisma.endUser.update({
    where: { id: endUserId },
    data: { activeConversationId: conversation.id },
  });
  return prisma.conversation.update({
    where: { id: conversation.id },
    data: { lastMessageAt: new Date() },
  });
}

/** Most recent conversations for the "چت‌های قبلی" list, newest first. */
export function listRecentConversations(
  shopId: string,
  endUserId: string,
  take = 10,
): Promise<Conversation[]> {
  return prisma.conversation.findMany({
    where: { shopId, endUserId },
    orderBy: { lastMessageAt: "desc" },
    take,
  });
}
