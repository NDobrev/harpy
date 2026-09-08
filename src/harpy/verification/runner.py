"""Optional isolated Docker verification. Profiles are user-defined."""

from __future__ import annotations

from dataclasses import dataclass, field

from harpy.proc import CancelToken, run


@dataclass(frozen=True)
class RunnerProfile:
    image_digest: str
    command: list[str]
    workdir: str = "/work"
    env_allowlist: frozenset[str] = field(default_factory=frozenset)
    timeout: float = 600.0


class VerificationError(RuntimeError):
    pass


def docker_argv(profile: RunnerProfile, workspace: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--cpus",
        "2",
        "--memory",
        "2g",
        "--pids-limit",
        "256",
        "--tmpfs",
        "/tmp",
        "-w",
        profile.workdir,
        profile.image_digest,
        *profile.command,
    ]


def run_verification(profile: RunnerProfile, *, cancel: CancelToken | None = None) -> int:
    if not profile.image_digest.startswith("sha256:"):
        raise VerificationError("image digest required; will not pull")
    argv = docker_argv(profile, "/work")
    result = run(
        argv,
        timeout=profile.timeout,
        inherit_env=False,
        env_allowlist=profile.env_allowlist,
        cancel=cancel,
    )
    return result.returncode
