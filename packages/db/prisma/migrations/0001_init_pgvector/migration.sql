-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding columns to products
ALTER TABLE products ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Add embedding columns to faq_items
ALTER TABLE faq_items ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Add embedding columns to shop_info_chunks
ALTER TABLE shop_info_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create HNSW indexes for cosine similarity search
CREATE INDEX IF NOT EXISTS products_embedding_idx
  ON products USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS faq_items_embedding_idx
  ON faq_items USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS shop_info_chunks_embedding_idx
  ON shop_info_chunks USING hnsw (embedding vector_cosine_ops);
