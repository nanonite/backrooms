"""Model identity and the explicitly enabled OpenCode CLI adapter."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from seed_review_errors import SeedReviewError

OPENCODE_TIMEOUT_EXIT = 124
MAX_CAPTURED_ERROR_CHARS = 2000


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model: str
    image_input_supported: bool
    image_input_support_basis: str
    is_free: bool
    listed_price_usd: float | None
    accounting: str
    opencode_version: str | None = None

    @property
    def reference(self) -> str:
        return f"{self.provider}/{self.model}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "reference": self.reference,
            "image_input_supported": self.image_input_supported,
            "image_input_support_basis": self.image_input_support_basis,
            "is_free": self.is_free,
            "listed_price_usd": self.listed_price_usd,
            "accounting": self.accounting,
            "opencode_version": self.opencode_version,
        }


@dataclass(frozen=True)
class ModelInvocation:
    identity: ModelIdentity
    prompt: str
    image_paths: tuple[Path, ...]
    timeout_seconds: float


@dataclass(frozen=True)
class ProviderResponse:
    status: str
    raw_text: str
    usage_payload: dict[str, Any] | None
    error: str | None
    elapsed_seconds: float
    command: tuple[str, ...]


class SeedReviewModel(Protocol):
    def invoke(self, invocation: ModelInvocation) -> ProviderResponse:
        """Run one bounded request and return its raw provider result."""


class OpenCodeCliModel:
    """One-shot OpenCode invocation. Only constructed for an enabled live run."""

    def invoke(self, invocation: ModelInvocation) -> ProviderResponse:
        command = build_opencode_command(
            invocation.identity.reference,
            invocation.image_paths,
            invocation.prompt,
        )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=invocation.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            return ProviderResponse(
                status="timed_out",
                raw_text=_timeout_text(error),
                usage_payload=None,
                error=(
                    f"OpenCode exceeded the {invocation.timeout_seconds:g}s "
                    "timeout; no automatic retry"
                ),
                elapsed_seconds=round(time.monotonic() - started, 3),
                command=tuple(command),
            )
        except OSError as error:
            return ProviderResponse(
                status="error",
                raw_text="",
                usage_payload=None,
                error=f"Cannot start OpenCode: {error}",
                elapsed_seconds=round(time.monotonic() - started, 3),
                command=tuple(command),
            )
        elapsed = round(time.monotonic() - started, 3)
        if completed.returncode == OPENCODE_TIMEOUT_EXIT:
            return ProviderResponse(
                status="timed_out",
                raw_text=completed.stdout,
                usage_payload=None,
                error=f"OpenCode exited with timeout status {OPENCODE_TIMEOUT_EXIT}",
                elapsed_seconds=elapsed,
                command=tuple(command),
            )
        if completed.returncode != 0:
            return ProviderResponse(
                status="error",
                raw_text=completed.stdout,
                usage_payload=None,
                error=_provider_error(completed.stdout, completed.stderr),
                elapsed_seconds=elapsed,
                command=tuple(command),
            )
        return ProviderResponse(
            status="completed",
            raw_text=extract_response_text(completed.stdout),
            usage_payload=extract_usage_payload(completed.stdout),
            error=None,
            elapsed_seconds=elapsed,
            command=tuple(command),
        )


def build_opencode_command(
    reference: str, image_paths: tuple[Path, ...], prompt: str
) -> list[str]:
    command = ["opencode", "run", "--standalone", "--model", reference]
    for path in image_paths:
        command.extend(["--file", str(path)])
    command.extend(["--format", "json", prompt])
    return command


def detect_opencode_version(timeout_seconds: float = 10.0) -> str | None:
    try:
        completed = subprocess.run(
            ["opencode", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = completed.stdout.strip()
    return version or None


def enforce_model_policy(
    identity: ModelIdentity,
    hard_cost_ceiling_usd: float | None,
    provider_enforces_spend_limit: bool,
) -> bool:
    """Return whether a paid call is allowed; raise before any invocation."""
    if not identity.image_input_supported:
        raise SeedReviewError(
            "image_input_support_not_verified",
            "Image support must be verified before a frame-review model call",
        )
    if identity.is_free or identity.listed_price_usd == 0.0:
        return False
    if hard_cost_ceiling_usd is None or hard_cost_ceiling_usd <= 0:
        raise SeedReviewError(
            "paid_call_requires_hard_ceiling",
            "Paid model call requires a positive per-run USD ceiling",
        )
    if not provider_enforces_spend_limit:
        raise SeedReviewError(
            "paid_call_requires_accounting",
            "Paid model call requires a provider spend limit or reliable "
            "usage accounting",
        )
    return True


def extract_usage_payload(text: str) -> dict[str, Any] | None:
    """Best-effort usage extraction from an OpenCode JSON event stream."""
    payload = _parse_json_documents(text)
    if payload is None:
        return None
    return payload if _contains_usage(payload) else None


def extract_response_text(text: str) -> str:
    """Join OpenCode JSON text events, falling back to ordinary model text."""
    parts = _text_event_parts(text)
    return "\n".join(parts) if parts else text


def _text_event_parts(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        value = part.get("text") if isinstance(part, dict) else None
        if event.get("type") == "text" and isinstance(value, str):
            parts.append(value)
    return parts


def _parse_json_documents(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    merged: dict[str, Any] = {}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            merged.update(event)
    return merged or None


def _contains_usage(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {
                "usage",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cost",
                "cost_usd",
            }:
                return True
            if _contains_usage(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_usage(item) for item in value)
    return False


def _timeout_text(error: subprocess.TimeoutExpired) -> str:
    output = error.output or ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _provider_error(stdout: str, stderr: str) -> str:
    event_message = _error_event_message(stdout)
    return _truncated(event_message or stderr or "OpenCode returned nonzero")


def _error_event_message(text: str) -> str | None:
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "error":
            continue
        error = event.get("error")
        if not isinstance(error, dict):
            continue
        details = [
            value
            for value in (
                error.get("type"),
                error.get("message"),
                f"HTTP {error['status']}"
                if isinstance(error.get("status"), int)
                else None,
            )
            if isinstance(value, str) and value
        ]
        if details:
            return ": ".join(details)
    return None


def _truncated(text: str) -> str:
    return text[-MAX_CAPTURED_ERROR_CHARS:]
