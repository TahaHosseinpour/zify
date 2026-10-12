import { prisma } from "./index";

// A shop reaches its customers through channels, and each kind is simply on
// or off: the Telegram bot, and the chat widget embedded in the shop's own
// site. "On" means the shop has at least one active Channel row of that type.
export const CHANNEL_TYPES = ["telegram", "widget"] as const;
export type ChannelType = (typeof CHANNEL_TYPES)[number];

export function isChannelType(value: unknown): value is ChannelType {
  return typeof value === "string" && (CHANNEL_TYPES as readonly string[]).includes(value);
}

export async function isChannelActive(shopId: string, type: ChannelType): Promise<boolean> {
  const active = await prisma.channel.findFirst({
    where: { shopId, type, isActive: true },
    select: { id: true },
  });
  return active !== null;
}

/** Turn one kind of channel on or off for a shop. Older shops can hold several
 * rows of the same type (the panel used to add one per click), so every row of
 * the type follows the switch. */
export async function setChannelActive(
  shopId: string,
  type: ChannelType,
  active: boolean,
): Promise<void> {
  const { count } = await prisma.channel.updateMany({
    where: { shopId, type },
    data: { isActive: active },
  });
  if (count === 0 && active) {
    await prisma.channel.create({ data: { shopId, type } });
  }
}
