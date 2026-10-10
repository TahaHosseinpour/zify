"""Puts the sample shop into the real local database.

The scenarios run the production graph end to end - the real SQL filter, the
real pgvector search - so the catalog has to live where that code looks for it.
Everything created here is namespaced (dataset.ID_PREFIX / SHOP_SLUG) and
`seed()` replaces it wholesale each run, so it never touches a real shop and a
changed description never leaves a stale embedding behind.
"""

from __future__ import annotations

import asyncio

from app import graph as G
from app.db import db

import dataset as first_shop
from dataset import ID_PREFIX

SHOP_ID = ID_PREFIX + "shop"
OWNER_ID = ID_PREFIX + "owner"
OWNER_MOBILE = "comparison-eval"


# The provider's gateway times out now and then (a 504 from nginx), and more
# readily on a large batch. Seeding is the one step the whole run depends on,
# so it asks for a few texts at a time and tries again before giving up.
EMBED_BATCH_SIZE = 8
EMBED_ATTEMPTS = 5


async def _embed_with(client, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        for attempt in range(1, EMBED_ATTEMPTS + 1):
            try:
                vectors += await client.aembed_documents(batch)
                break
            except Exception as exc:  # noqa: BLE001 - retried, then re-raised
                if attempt == EMBED_ATTEMPTS:
                    raise
                wait = 3 * attempt
                print(f"  embedding call failed ({type(exc).__name__}); retrying in {wait}s ...", flush=True)
                await asyncio.sleep(wait)
    return vectors


async def _embed_all(texts: list[str]) -> dict[str, list[list[float]]]:
    """The texts embedded by every provider the run can use, keyed by the
    column each provider's vectors are stored in - the same two columns the
    admin panel writes (packages/db/src/embeddings.ts). A provider the
    pre-flight check found down (its breaker is open) is left out, and its
    column stays empty."""
    by_column: dict[str, list[list[float]]] = {}
    for space, client in G._embedding_chain():
        if G._embedding_breaker(space).available():
            by_column[space.column] = await _embed_with(client, texts)
    if not by_column:
        raise RuntimeError("no embedding provider is available")
    return by_column


async def _store_vectors(table: str, row_id: str, index: int, by_column: dict[str, list[list[float]]]) -> None:
    for column, vectors in by_column.items():
        await db.execute_raw(
            f"UPDATE {table} SET {column} = $1::vector WHERE id = $2", _vector(vectors[index]), row_id
        )


def _vector(vec: list[float]) -> str:
    return "[" + ",".join(str(v) for v in G._pad_to_dim(vec)) + "]"


async def clear() -> None:
    for table in ("products", "faq_items", "shop_info_chunks"):
        await db.execute_raw(f'DELETE FROM {table} WHERE "shopId" = $1', SHOP_ID)
    await db.execute_raw("DELETE FROM shops WHERE id = $1", SHOP_ID)
    await db.execute_raw("DELETE FROM users WHERE id = $1", OWNER_ID)


async def seed(data=None) -> str:
    """(Re)create a sample shop with embeddings. Returns its id.

    `data` is a module of the shape of dataset.py (the default) - the second
    shop, dataset_beauty.py, is seeded under the same id, so one run holds one
    shop and clear() removes whichever it was.
    """
    data = data or first_shop
    await clear()
    await db.execute_raw(
        """INSERT INTO users (id, mobile, "isVerified", "onboardingCompleted", "updatedAt")
           VALUES ($1, $2, true, true, now())""",
        OWNER_ID,
        OWNER_MOBILE,
    )
    await db.execute_raw(
        """INSERT INTO shops (id, slug, name, categories, "personaTone", "ownerId")
           VALUES ($1, $2, $3, $4::text[], 'semi-formal', $5)""",
        SHOP_ID,
        data.SHOP_SLUG,
        data.SHOP_NAME,
        data.CATEGORIES,
        OWNER_ID,
    )

    # One batched embedding call per kind. The embedded text mirrors what the
    # admin panel embeds for each (apps/admin/app/api/products/route.ts and
    # apps/admin/lib/embeddings.ts): name + description + category + brand for
    # a product, the question for an FAQ entry, the content for shop info.
    product_vecs = await _embed_all(
        [" ".join([p.name, p.description, p.category, p.brand]) for p in data.PRODUCTS]
    )
    for i, product in enumerate(data.PRODUCTS):
        await db.execute_raw(
            """INSERT INTO products
                 (id, "shopId", name, price, "productUrl", description, category, brand, stock)
               VALUES ($1, $2, $3, $4::numeric, $5, $6, $7, $8, 10)""",
            product.id,
            SHOP_ID,
            product.name,
            str(product.price),
            product.url,
            product.description,
            product.category,
            product.brand,
        )
        await _store_vectors("products", product.id, i, product_vecs)

    faq_vecs = await _embed_all([question for question, _ in data.FAQS])
    for i, (question, answer) in enumerate(data.FAQS):
        await db.execute_raw(
            """INSERT INTO faq_items (id, "shopId", question, answer)
               VALUES ($1, $2, $3, $4)""",
            f"{ID_PREFIX}faq-{i}",
            SHOP_ID,
            question,
            answer,
        )
        await _store_vectors("faq_items", f"{ID_PREFIX}faq-{i}", i, faq_vecs)

    info_vecs = await _embed_all(data.SHOP_INFO)
    for i, content in enumerate(data.SHOP_INFO):
        await db.execute_raw(
            """INSERT INTO shop_info_chunks (id, "shopId", content)
               VALUES ($1, $2, $3)""",
            f"{ID_PREFIX}info-{i}",
            SHOP_ID,
            content,
        )
        await _store_vectors("shop_info_chunks", f"{ID_PREFIX}info-{i}", i, info_vecs)
    return SHOP_ID
