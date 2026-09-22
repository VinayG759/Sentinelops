"""Start the API server:  uv run python run.py

Why not plain `uvicorn app.main:app`? On Windows, asyncio defaults to the
ProactorEventLoop, which psycopg (our Postgres driver) cannot use in async mode.
This launcher runs uvicorn on a SelectorEventLoop, which works on every OS.
"""

import asyncio
import sys

import uvicorn


def main() -> None:
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=8000))
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
