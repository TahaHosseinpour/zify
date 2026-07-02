import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT", "3001"))
    reload = os.environ.get("RELOAD", "false").lower() == "true"
    print(f"[agent] starting on port {port}")
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        loop="none",
    )
