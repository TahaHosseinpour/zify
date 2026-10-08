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
    # Loopback by default: the only callers are the admin panel and the bot on
    # this same machine (AGENT_URL is http://localhost:<port>). Listening on
    # every interface would put the service that spends the model budget on
    # the public network, with only its shared key in front of it.
    host = os.environ.get("AGENT_HOST", "127.0.0.1")
    print(f"[agent] starting on {host}:{port}")
    uvicorn.run(
        "app.server:app",
        host=host,
        port=port,
        reload=reload,
        loop="none",
    )
