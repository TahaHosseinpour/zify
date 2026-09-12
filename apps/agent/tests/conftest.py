"""Shared fixtures for the agent test suite.

Two tiers of tests live here:

- Pure/unit tests exercise graph.py's helper functions directly — no DB, no
  LLM, no network. These run anywhere, always.
- DB-backed tests talk to the real Postgres/pgvector instance from
  docker-compose.yml, because the whole point of the SQL filter step is
  behaviour a mock cannot verify (placeholder indices, ILIKE case-folding,
  numeric bounds, HNSW-scoped vector search). They're skipped automatically
  when the database is unreachable rather than failing the whole run.

Nothing here calls OpenAI. The LLM and embedding calls are stubbed at the
`graph.llm` / `graph.embeddings` seam in every test that needs one — the agent
key's monthly quota was exhausted for the whole of this project's development,
so no test may depend on it being available.
"""

import asyncio
import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(AGENT_ROOT.parent.parent / ".env")

from app import graph as G  # noqa: E402
from app.db import db  # noqa: E402

# Matches main.py: Prisma's engine subprocess needs the selector policy on
# Windows. Set directly rather than through pytest-asyncio's (deprecated)
# event_loop_policy fixture.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests under tests/db_/ as requiring the database."""
    for item in items:
        if "db" in item.keywords:
            continue
        if "/db_" in str(item.fspath).replace("\\", "/") or item.fspath.purebasename.startswith("test_db"):
            item.add_marker(pytest.mark.db)


@pytest.fixture(scope="session")
async def real_db():
    """Connect to the live Postgres instance; skip DB-marked tests if it is
    unreachable rather than failing the whole suite on an environment issue."""
    try:
        if not db.is_connected():
            await db.connect()
        await db.query_raw("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database unavailable: {exc}")
    yield db


@pytest.fixture(scope="session")
async def shop_id(real_db):
    """The first shop in the dev database that actually has embedded products —
    the fixture data this whole project has been developed against."""
    rows = await real_db.query_raw(
        """SELECT DISTINCT p."shopId" AS id FROM products p
           WHERE p.embedding IS NOT NULL LIMIT 1"""
    )
    if not rows:
        pytest.skip("no shop with embedded products in the database")
    return str(rows[0]["id"])


def item(id_, typ="product", price=None, score=0.5, url=None, image=None):
    """Build a RetrievedItem for tests without going through the DB."""
    meta = {"name": f"name-{id_}"}
    if price is not None:
        meta["price"] = price
    if url is not None:
        meta["productUrl"] = url
    if image is not None:
        meta["imageUrl"] = image
    return {"id": id_, "type": typ, "content": f"content-{id_}", "score": score, "metadata": meta}


class FakeShop:
    """Minimal object satisfying prompts.ShopPersona for stubbed LLM nodes."""

    def __init__(self, name="فروشگاه تست"):
        self.name = name
        self.description = None
        self.categories = ["کفش", "لپ‌تاپ"]
        self.supportInfo = None
        self.personaCharacter = None
        self.personaTone = "formal"
        self.systemPromptExtra = None


@pytest.fixture
def fake_llm(monkeypatch):
    """Stub graph.llm.ainvoke to return a fixed AIMessage and record every
    call's messages, so a test can assert on what the prompt actually said."""
    from langchain_core.messages import AIMessage

    calls = []

    async def fake_ainvoke(messages):
        calls.append(messages)
        return AIMessage(content="پاسخ آزمایشی")

    class FakeLLM:
        ainvoke = staticmethod(fake_ainvoke)

    monkeypatch.setattr(G, "llm", FakeLLM())
    return calls


@pytest.fixture
def fake_shop_db(monkeypatch):
    """Stub graph.db.shop.find_unique and graph.db.product.find_first so nodes
    that look up the shop/pinned product don't need a live database."""
    products: dict[str, object] = {}

    class FakeShopTable:
        @staticmethod
        async def find_unique(**kw):
            return FakeShop()

    class FakeProductTable:
        @staticmethod
        async def find_first(where, **kw):
            return products.get(where["id"])

    class FakeDB:
        shop = FakeShopTable()
        product = FakeProductTable()

    monkeypatch.setattr(G, "db", FakeDB())
    return products
