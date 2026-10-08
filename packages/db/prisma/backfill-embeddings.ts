/**
 * Fill empty embedding columns on products, FAQ items and shop-info chunks.
 *
 * Every row keeps one vector per embedding provider (packages/db/src/
 * embeddings.ts). A column is empty when the row predates it — everything
 * saved before migration 0005 has no `embedding_gemini` — or when its provider
 * was down while the row was saved. Until it is filled, the agent cannot find
 * that row through that provider.
 *
 *   bun run db:backfill-embeddings [--shop <id>]
 *
 * Safe to re-run: only empty columns are requested. Exits 0 even when some
 * rows could not be embedded (a provider being down must not fail a deploy);
 * the counts are printed, and the next run picks up what is left.
 */
import { backfillEmbeddings, geminiEmbeddingsEnabled, prisma } from "../src/index"

async function main() {
  const shopFlag = process.argv.indexOf("--shop")
  const shopId = shopFlag >= 0 ? process.argv[shopFlag + 1] : undefined

  if (!geminiEmbeddingsEnabled()) {
    console.log("GEMINI_BASE_URL is not set - only the primary embedding column will be filled.")
  }

  const result = await backfillEmbeddings({
    shopId,
    onProgress: (table, done, total) => {
      if (done === total || done % 25 === 0) console.log(`  ${table}: ${done}/${total}`)
    },
  })

  console.log(`Embeddings backfilled: ${result.filled} written, ${result.failed} failed.`)
  if (result.failed > 0) {
    console.warn("Some embeddings could not be written - run this again once the provider is back.")
  }
}

main()
  .catch((err) => {
    console.error("Embedding backfill did not run:", err)
  })
  .finally(() => prisma.$disconnect())
