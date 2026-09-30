"""Grant the first Pi operator role to an existing Owner OS user (server-side only).

Usage (from apps/api, with the target database configured):

    python -m app.modules.pi_saas.bootstrap_operator owner@example.com [role]

There is deliberately no HTTP route for this: after the first operator owner exists,
further operators are managed in the Owner OS operator console (Operator team).
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models  # noqa: F401  (register every mapper so foreign keys resolve)
from app.core.config import get_settings
from app.core.database import create_engine
from app.modules.audit.service import record
from app.modules.pi_saas.models import OPERATOR_ROLES, PiOperatorMember
from app.modules.users.models import PlatformUser


async def main(email: str, role: str) -> int:
    if role not in OPERATOR_ROLES:
        print(f"Unknown role. Choose one of: {', '.join(OPERATOR_ROLES)}")
        return 2
    engine = create_engine(get_settings())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            user = await session.scalar(
                select(PlatformUser).where(PlatformUser.email == email.strip().lower())
            )
            if user is None:
                print("No Owner OS account with that email. Register it first.")
                return 1
            member = await session.scalar(
                select(PiOperatorMember).where(PiOperatorMember.user_id == user.id)
            )
            if member is None:
                member = PiOperatorMember(user_id=user.id, role=role)
                session.add(member)
            member.role, member.status = role, "active"
            await session.flush()
            await record(
                session,
                "pi_operator.bootstrapped",
                actor_user_id=None,
                entity_type="pi_operator",
                entity_id=member.id,
                details={"role": role},
            )
            await session.commit()
            print(f"{email} is now a Pi operator ({role}).")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "owner")))
