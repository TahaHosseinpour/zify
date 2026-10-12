import { Prisma } from "@prisma/client";
import { prisma } from "./index";

// Every row the agent retrieves (products, faq_items, shop_info_chunks) keeps
// one vector per embedding provider, each a fixed vector(1536):
//
//   embedding         OpenAI text-embedding-3-small (or the local model)
//   embedding_gemini  gemini-embedding-001, the agent's fallback provider
//
// Vectors from two models cannot be compared, so the agent can only answer a
// query with its second provider if the rows were embedded by that provider
// too (apps/agent/app/graph.py, PRIMARY_SPACE / GEMINI_SPACE). Both are
// written here on every save; when one provider is down the other is still
// written, and backfillEmbeddings fills the gap later.
//
// Mirrors apps/agent/app/graph.py's EMBEDDING_DIM / _pad_to_dim — both
// write/read paths must pad to the same width, or a local model's shorter
// vectors would silently stop matching the ones written by this file (and
// vice versa). See that file's comment for why zero-padding leaves cosine
// distance exact rather than approximate.
const EMBEDDING_DIM = 1536;

// A provider that accepts the connection and then sends nothing must not hold
// up saving a product.
const EMBEDDING_TIMEOUT_MS = 15_000;

export type EmbeddingColumn = "embedding" | "embedding_gemini";
export type EmbeddedTable = "products" | "faq_items" | "shop_info_chunks";

function localModelsEnabled(): boolean {
  const val = process.env.USE_LOCAL_MODELS;
  return val != null && ["1", "true", "yes", "on"].includes(val.trim().toLowerCase());
}

function padToDim(vec: number[], dim = EMBEDDING_DIM): number[] {
  if (vec.length === dim) return vec;
  if (vec.length > dim) {
    throw new Error(
      `embedding dim ${vec.length} exceeds the pgvector column width ${dim} — ` +
        "truncating would silently corrupt cosine distance; this model can't be " +
        "used against the current schema without a migration.",
    );
  }
  return [...vec, ...new Array(dim - vec.length).fill(0)];
}

async function primaryEmbedding(text: string): Promise<number[]> {
  // Same USE_LOCAL_MODELS switch as the agent (apps/agent/app/graph.py) —
  // kept in sync so a product embedded here and a customer query embedded by
  // the agent are always produced by the same model. Never set in
  // production; see deploy/templates/setup-env.sh.j2.
  const local = localModelsEnabled();
  const baseUrl = (
    local
      ? (process.env.OLLAMA_BASE_URL ?? "http://localhost:11434/v1")
      : (process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1")
  ).replace(/\/$/, "");
  const model = local
    ? (process.env.OLLAMA_EMBEDDING_MODEL ?? "bge-m3")
    : (process.env.OPENAI_EMBEDDING_MODEL ?? "text-embedding-3-small");
  const apiKey = local ? "ollama" : process.env.OPENAI_API_KEY;

  // The same model through a second gateway (AVALAI_*, as in the agent), asked
  // first when it is configured: either gateway's vector belongs in this
  // column, so a save only fails when both are down.
  const endpoints = [{ baseUrl, model, apiKey }];
  const avalaiUrl = (process.env.AVALAI_BASE_URL ?? "").replace(/\/$/, "");
  if (!local && avalaiUrl && process.env.AVALAI_API_KEY) {
    endpoints.unshift({
      baseUrl: avalaiUrl,
      model: process.env.AVALAI_EMBEDDING_MODEL ?? "text-embedding-3-small",
      apiKey: process.env.AVALAI_API_KEY,
    });
  }

  let lastError: unknown;
  for (const endpoint of endpoints) {
    try {
      const res = await fetch(`${endpoint.baseUrl}/embeddings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${endpoint.apiKey}`,
        },
        body: JSON.stringify({ model: endpoint.model, input: text }),
        signal: local ? undefined : AbortSignal.timeout(EMBEDDING_TIMEOUT_MS),
      });
      if (!res.ok) throw new Error(`embeddings request failed: ${res.status} ${await res.text()}`);
      const data = (await res.json()) as { data: { embedding: number[] }[] };
      return padToDim(data.data[0].embedding);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

/** The second provider is in use only when its base URL is configured — the
 * same rule as the agent (GEMINI_BASE_URL in apps/agent/app/graph.py). */
export function geminiEmbeddingsEnabled(): boolean {
  return !localModelsEnabled() && Boolean(process.env.GEMINI_BASE_URL);
}

async function geminiEmbedding(text: string): Promise<number[]> {
  const baseUrl = (process.env.GEMINI_BASE_URL ?? "").replace(/\/$/, "");
  const model = process.env.GEMINI_EMBEDDING_MODEL ?? "gemini-embedding-001";
  const res = await fetch(`${baseUrl}/models/${model}:embedContent`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": process.env.GEMINI_API_KEY || process.env.OPENAI_API_KEY || "",
    },
    body: JSON.stringify({
      model: `models/${model}`,
      content: { parts: [{ text }] },
      // What is stored is always the document side; the agent embeds the
      // customer's message as RETRIEVAL_QUERY.
      taskType: "RETRIEVAL_DOCUMENT",
      outputDimensionality: EMBEDDING_DIM,
    }),
    signal: AbortSignal.timeout(EMBEDDING_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`gemini embeddings request failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return padToDim(data.embedding.values as number[]);
}

const PROVIDERS: Record<EmbeddingColumn, (text: string) => Promise<number[]>> = {
  embedding: primaryEmbedding,
  embedding_gemini: geminiEmbedding,
};

function activeColumns(): EmbeddingColumn[] {
  return geminiEmbeddingsEnabled() ? ["embedding", "embedding_gemini"] : ["embedding"];
}

function vectorToSql(vec: number[]): string {
  return `[${vec.join(",")}]`;
}

/**
 * Embed `text` with every configured provider and store each vector in its
 * own column. Returns the columns that were written.
 *
 * One provider failing does not stop the other from being stored: the row
 * stays searchable through the provider that answered. Its other column keeps
 * whatever it held (a slightly stale vector still finds an edited product; an
 * empty one would hide it). Throws only when nothing could be written.
 */
export async function embedRow(
  table: EmbeddedTable,
  id: string,
  text: string,
  columns: EmbeddingColumn[] = activeColumns(),
): Promise<EmbeddingColumn[]> {
  const results = await Promise.allSettled(columns.map((column) => PROVIDERS[column](text)));

  const written: EmbeddingColumn[] = [];
  const errors: unknown[] = [];
  for (const [i, result] of results.entries()) {
    const column = columns[i];
    if (result.status === "rejected") {
      errors.push(result.reason);
      console.warn(`[embeddings] ${table}.${column} not written for ${id}:`, result.reason);
      continue;
    }
    // Table and column come from the unions above, never from input.
    await prisma.$executeRaw`
      UPDATE ${Prisma.raw(table)} SET ${Prisma.raw(column)} = ${vectorToSql(result.value)}::vector
      WHERE id = ${id}
    `;
    written.push(column);
  }

  if (written.length === 0 && errors.length > 0) throw errors[0];
  return written;
}

export const embedProduct = (productId: string, text: string) => embedRow("products", productId, text);
export const embedFaq = (faqId: string, text: string) => embedRow("faq_items", faqId, text);
export const embedShopInfoChunk = (chunkId: string, text: string) =>
  embedRow("shop_info_chunks", chunkId, text);

/** The text a product is embedded as. category/brand are part of it so the
 * vector step ranks on them too. */
export function productEmbedText(p: {
  name: string;
  description?: string | null;
  category?: string | null;
  brand?: string | null;
}): string {
  return [p.name, p.description, p.category, p.brand].filter(Boolean).join(" ");
}

/** Embed the answer too: a customer's wording usually matches what the answer
 * says, not the way the question was phrased. */
export function faqEmbedText(f: { question: string; answer: string }): string {
  return [f.question, f.answer].filter(Boolean).join(" ");
}

interface MissingRow {
  id: string;
  text: string;
  missing_primary: boolean;
  missing_gemini: boolean;
}

const BACKFILL_SOURCES: Record<EmbeddedTable, string> = {
  products: `concat_ws(' ', name, description, category, brand)`,
  faq_items: `concat_ws(' ', question, answer)`,
  shop_info_chunks: `content`,
};

const BACKFILL_CONCURRENCY = 4;

export interface BackfillResult {
  filled: number;
  failed: number;
}

/**
 * Fill whichever embedding column is empty, for every row that has one empty:
 * rows that predate the second column, and rows saved while one provider was
 * down. Only the missing column is requested, so re-running it costs nothing
 * for rows that are already complete.
 */
export async function backfillEmbeddings(
  options: { shopId?: string; onProgress?: (table: EmbeddedTable, done: number, total: number) => void } = {},
): Promise<BackfillResult> {
  const gemini = geminiEmbeddingsEnabled();
  const total: BackfillResult = { filled: 0, failed: 0 };

  for (const table of Object.keys(BACKFILL_SOURCES) as EmbeddedTable[]) {
    const shopFilter = options.shopId ? Prisma.sql`AND "shopId" = ${options.shopId}` : Prisma.empty;
    const rows = await prisma.$queryRaw<MissingRow[]>`
      SELECT id,
             ${Prisma.raw(BACKFILL_SOURCES[table])} AS text,
             embedding IS NULL AS missing_primary,
             embedding_gemini IS NULL AS missing_gemini
      FROM ${Prisma.raw(table)}
      WHERE (embedding IS NULL OR (${gemini} AND embedding_gemini IS NULL))
        ${shopFilter}
    `;

    let done = 0;
    const queue = [...rows];
    const worker = async () => {
      for (let row = queue.shift(); row; row = queue.shift()) {
        const columns: EmbeddingColumn[] = [];
        if (row.missing_primary) columns.push("embedding");
        if (gemini && row.missing_gemini) columns.push("embedding_gemini");
        try {
          if (!row.text?.trim()) throw new Error("row has no text to embed");
          const written = await embedRow(table, row.id, row.text, columns);
          total.filled += written.length;
          total.failed += columns.length - written.length;
        } catch {
          total.failed += columns.length;
        }
        options.onProgress?.(table, ++done, rows.length);
      }
    };
    await Promise.all(Array.from({ length: BACKFILL_CONCURRENCY }, worker));
  }

  return total;
}
