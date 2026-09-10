-- Indexes for the SQL pre-filter step of the sales agent's retrieval pipeline.
--
-- Every product query starts with `"shopId" = $1 AND "isActive" = true AND
-- embedding IS NOT NULL` and then adds category / brand / price predicates.
-- The products table previously carried no index at all besides its primary
-- key, so each of those was a sequential scan — including the ones the vector
-- search runs on every turn.

-- Covers the predicate every query shares. Partial on the two constants so the
-- index stays small and matches the exact shape of the WHERE clause.
CREATE INDEX IF NOT EXISTS products_shop_active_idx
  ON products ("shopId")
  WHERE "isActive" = true AND embedding IS NOT NULL;

-- The category filter is now an exact match, so a btree on (shopId, category)
-- serves it directly. lower() to match the case-insensitive comparison.
CREATE INDEX IF NOT EXISTS products_shop_category_idx
  ON products ("shopId", lower(category));

CREATE INDEX IF NOT EXISTS products_shop_brand_idx
  ON products ("shopId", lower(brand));

-- Serves both the price range predicates and the ORDER BY price used to answer
-- "the cheapest one".
CREATE INDEX IF NOT EXISTS products_shop_price_idx
  ON products ("shopId", price);
