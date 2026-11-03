"""Count the old opening ("going wrong in your business", "I'll start on it", and the Roman Urdu and
Urdu forms) in pi's stored replies (spec v1.5 18.2, the 1,000-reply scan). Read-only.

Refuses any database that is not the disposable test one unless --url is given on purpose, so the
real database is never read by accident. Usage (from apps/api, repo .venv, after the test env):
    python scripts/pi_scan_old_greeting.py [--limit 1000] [--url postgresql://...]
Prints the number scanned, the number that hit, and a short cut sample of each hit. No model call.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.modules.pi.evalkit import greeting_scan  # noqa: E402
from app.modules.pi.models import PiMessage  # noqa: E402

DISPOSABLE = "127.0.0.1:55432/owner_industry_test"


def async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def main(limit: int, url: str) -> int:
    engine = create_async_engine(async_url(url))
    try:
        async with async_sessionmaker(engine)() as session:
            rows = await session.scalars(
                select(PiMessage.body)
                .where(PiMessage.direction == "outbound")
                .order_by(PiMessage.created_at.desc())
                .limit(limit)
            )
            report = greeting_scan.scan(("outbound", body or "") for body in rows)
    finally:
        await engine.dispose()
    print(f"scanned {report['scanned']} outbound replies, {report['hits']} with the old opening")
    for where, sample in report["samples"]:
        print(f"  {where}: ...{sample}")
    return 1 if report["hits"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()
    if DISPOSABLE not in args.url and "--url" not in sys.argv:
        sys.exit(f"refusing: DATABASE_URL is not the disposable database ({DISPOSABLE})")
    sys.exit(asyncio.run(main(args.limit, args.url)))
