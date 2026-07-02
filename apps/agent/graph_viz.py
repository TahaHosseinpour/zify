import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: E402

from app.graph import build_graph  # noqa: E402


async def main():
    async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as checkpointer:
        graph = build_graph(checkpointer)
        png = graph.get_graph().draw_mermaid_png()
        output_path = Path(__file__).resolve().parent / "graph.png"
        output_path.write_bytes(png)
        print(f"[graph-viz] saved {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
