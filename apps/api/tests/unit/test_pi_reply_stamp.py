"""Platform spec A.2 #8 and A.8: every reply logs the prompt, pack and build versions."""

from types import SimpleNamespace
from uuid import uuid4

from app.modules.pi import learning_audit


def test_the_build_id_is_the_deployed_commit_and_never_a_secret(monkeypatch):
    for name in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION", "COMMIT_SHA"):
        monkeypatch.delenv(name, raising=False)
    assert learning_audit.build_id() == "unknown"
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123def4567890ffff")
    assert learning_audit.build_id() == "abc123def456"


class _BrokenSession:
    """A session whose savepoint works but whose statements fail (a missing table, a constraint)."""

    def begin_nested(self):
        class _Ctx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False  # let the error through, as a real savepoint does

        return _Ctx()

    async def scalar(self, *a, **k):
        raise RuntimeError("relation does not exist")


async def test_a_failing_stamp_never_fails_the_reply():
    conversation = SimpleNamespace(id=uuid4(), service_brief={})
    scope = SimpleNamespace(tenant_id=uuid4(), environment_id=uuid4())
    reply = SimpleNamespace(id=uuid4())
    await learning_audit.stamp_safely(_BrokenSession(), scope, conversation, reply)  # no raise
