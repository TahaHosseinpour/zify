"""Puts the sample shop into the real local database.

The scenarios run the production graph end to end - the real SQL filter, the
real pgvector search - so the catalog has to live where that code looks for it.
Everything created here is namespaced (dataset.ID_PREFIX / SHOP_SLUG) and
`seed()` replaces it wholesale each run, so it never touches a real shop and a
changed description never leaves a stale embedding behind.
"""

from __future__ import annotations

from app import graph as G
from app.db import db

from dataset import CATEGORIES, FAQS, ID_PREFIX, PRODUCTS, SHOP_INFO, SHOP_NAME, SHOP_SLUG

SHOP_ID = ID_PREFIX + "shop"
OWNER_ID = ID_PREFIX + "owner"
OWNER_MOBILE = "comparison-eval"


def _vector(vec: list[float]) -> str:
    return "[" + ",".join(str(v) for v in G._pad_to_dim(vec)) + "]"


async def clear() -> None:
    for table in ("products", "faq_items", "shop_info_chunks"):
        await db.execute_raw(f'DELETE FROM {table} WHERE "shopId" = $1', SHOP_ID)
    await db.execute_raw("DELETE FROM shops WHERE id = $1", SHOP_ID)
    await db.execute_raw("DELETE FROM users WHERE id = $1", OWNER_ID)


async def seed() -> str:
    """(Re)create the sample shop with embeddings. Returns its id."""
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
        SHOP_SLUG,
        SHOP_NAME,
        CATEGORIES,
        OWNER_ID,
    )

    # One batched embedding call per kind. The embedded text mirrors what the
    # admin panel embeds for each (apps/admin/app/api/products/route.ts and
    # apps/admin/lib/embeddings.ts): name + description + category + brand for
    # a product, the question for an FAQ entry, the content for shop info.
    product_vecs = await G.embeddings.aembed_documents(
        [" ".join([p.name, p.description, p.category, p.brand]) for p in PRODUCTS]
    )
    for product, vec in zip(PRODUCTS, product_vecs):
        await db.execute_raw(
            """INSERT INTO products
                 (id, "shopId", name, price, "productUrl", description, category, brand, stock, embedding)
               VALUES ($1, $2, $3, $4::numeric, $5, $6, $7, $8, 10, $9::vector)""",
            product.id,
            SHOP_ID,
            product.name,
            str(product.price),
            product.url,
            product.description,
            product.category,
            product.brand,
            _vector(vec),
        )

    faq_vecs = await G.embeddings.aembed_documents([question for question, _ in FAQS])
    for i, ((question, answer), vec) in enumerate(zip(FAQS, faq_vecs)):
        await db.execute_raw(
            """INSERT INTO faq_items (id, "shopId", question, answer, embedding)
               VALUES ($1, $2, $3, $4, $5::vector)""",
            f"{ID_PREFIX}faq-{i}",
            SHOP_ID,
            question,
            answer,
            _vector(vec),
        )

    info_vecs = await G.embeddings.aembed_documents(SHOP_INFO)
    for i, (content, vec) in enumerate(zip(SHOP_INFO, info_vecs)):
        await db.execute_raw(
            """INSERT INTO shop_info_chunks (id, "shopId", content, embedding)
               VALUES ($1, $2, $3, $4::vector)""",
            f"{ID_PREFIX}info-{i}",
            SHOP_ID,
            content,
            _vector(vec),
        )
    return SHOP_ID
