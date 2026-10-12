-- The bot now answers only for a shop whose Telegram channel is switched on
-- (packages/db/src/channels.ts). Until now it answered every shop, channel row
-- or not, so a shop that has no Telegram row at all gets an active one here:
-- nothing stops working on the day this ships. A shop that already has rows
-- keeps them exactly as they are.
INSERT INTO channels (id, "shopId", type, "isActive", "createdAt")
SELECT 'ch_' || md5(random()::text || s.id), s.id, 'telegram', true, now()
FROM shops s
WHERE NOT EXISTS (
  SELECT 1 FROM channels c WHERE c."shopId" = s.id AND c.type = 'telegram'
);
