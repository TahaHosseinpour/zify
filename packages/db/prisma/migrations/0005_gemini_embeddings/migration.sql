-- A second embedding per row, written by the fallback embedding provider
-- (gemini-embedding-001, requested at 1536 dimensions). Vectors from two
-- models cannot be compared, so the agent can only fall back to the second
-- provider for a query if every row also has a vector from that provider.
ALTER TABLE products ADD COLUMN IF NOT EXISTS embedding_gemini vector(1536);

ALTER TABLE faq_items ADD COLUMN IF NOT EXISTS embedding_gemini vector(1536);

ALTER TABLE shop_info_chunks ADD COLUMN IF NOT EXISTS embedding_gemini vector(1536);

CREATE INDEX IF NOT EXISTS products_embedding_gemini_idx
  ON products USING hnsw (embedding_gemini vector_cosine_ops);

CREATE INDEX IF NOT EXISTS faq_items_embedding_gemini_idx
  ON faq_items USING hnsw (embedding_gemini vector_cosine_ops);

CREATE INDEX IF NOT EXISTS shop_info_chunks_embedding_gemini_idx
  ON shop_info_chunks USING hnsw (embedding_gemini vector_cosine_ops);
