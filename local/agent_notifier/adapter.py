"""Capability-aware adapters over existing bridge implementations.

No subprocess is launched by creating an adapter. The existing bridge remains
responsible for agent execution and its local permission checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# These describe capabilities exposed by the CURRENT local bridge, not claims
# about every version of the underlying third-party agent CLI.
CAPABILITIES: dict[str, dict[str, bool]] = {
    "claude": {
        "notify": True, "prompt": True, "resume": True, "cancel": True,
        "list_sessions": False, "approval": False, "cloud_remote": False,
    },
    "codex": {
        "notify": True, "prompt": True, "resume": False, "cancel": True,
        "list_sessions": False, "approval": False, "cloud_remote": False,
    },
    "opencode": {
        "notify": True, "prompt": True, "resume": True, "cancel": True,
        "list_sessions": False, "approval": False, "cloud_remote": False,
    },
    "custom": {
        "notify": False, "prompt": True, "resume": False, "cancel": True,
        "list_sessions": False, "approval": False, "cloud_remote": False,
    },
}


def capabilities_for(name: str) -> dict[str, bool]:
    """Return a defensive copy; never guess unverified support."""
    return dict(CAPABILITIES.get(name, CAPABILITIES["custom"]))


@dataclass
class AgentAdapter:
    """Uniform façade for existing bridge implementations.

    The adapter wraps the locally authorized bridge agent and does not
    authenticate remote requests. That belongs to a future cloud protocol.
    """
    name: str
    implementation: Any

    def supports(self, operation: str) -> bool:
        return bool(capabilities_for(self.name).get(operation, False))

    def build_command(self, message: str, session_id: str | None, permissions: str) -> list[str]:
        if not self.supports("prompt"):
            raise ValueError("agent does not support prompts")
        if permissions not in ("readonly", "edit", "full"):
            raise ValueError("unsupported permission level")
        if session_id and not self.supports("resume"):
            raise ValueError("session resume is unsupported")
        return self.implementation.build(message, session_id, permissions)

    def parse_output(self, stdout: str, stderr: str, returncode: int):
        return self.implementation.parse(stdout, stderr, returncode)


def from_local_bridge(name: str, template: str | None = None, settings=None) -> AgentAdapter | None:
    """Reuse the mature bridge's parser and command builder, without a rewrite."""
    from .bridge import make_agent

    impl = make_agent(name, template, settings)
    return AgentAdapter(name, impl) if impl else None
