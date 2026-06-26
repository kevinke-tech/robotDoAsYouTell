"""Unified runtime/synthesis error classification."""

from __future__ import annotations


_TRANSIENT_INVOKE_ERROR_HINTS = (
    "connecttimeout",
    "readtimeout",
    "pooltimeout",
    "timeout",
    "connecterror",
    "readerror",
    "writeerror",
    "remoteprotocolerror",
    "temporarily unavailable",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname provided",
    "connection reset by peer",
    "connection aborted",
    "service unavailable",
    "dns",
)

_RECOVERABLE_SYNTH_ERROR_HINTS = (
    "agent didn't produce a unique skill file",
    "cursor-sdk run failed",
    "cursor-sdk returned error status",
    "synthesis call timeout",
    "timed out",
    "networkerror",
    "remoteprotocolerror",
    "bridge request failed",
    "peer closed connection",
    "write confirmed",
    "error_no_code_fence",
)


def is_transient_external_error(err: str) -> bool:
    s = str(err or "").strip().lower()
    if not s:
        return False
    return any(h in s for h in _TRANSIENT_INVOKE_ERROR_HINTS)


def is_recoverable_synthesis_error(err: str) -> bool:
    s = str(err or "").strip().lower()
    if not s:
        return False
    return any(h in s for h in _RECOVERABLE_SYNTH_ERROR_HINTS)


def classify_error(err: str, stage: str = "invoke") -> dict:
    s = str(err or "").strip()
    low = s.lower()
    out = {
        "stage": stage,
        "error": s,
        "category": "unknown",
        "transient": False,
        "recoverable": False,
        "bad_args": False,
    }
    if low.startswith("bad args:"):
        out["category"] = "bad_args"
        out["bad_args"] = True
        out["recoverable"] = True
        return out

    if stage == "invoke":
        if is_transient_external_error(s):
            out["category"] = "transient_external"
            out["transient"] = True
            out["recoverable"] = True
            return out
        out["category"] = "invoke_failure"
        return out

    if stage == "synthesis":
        if is_recoverable_synthesis_error(s):
            out["category"] = "recoverable_synthesis"
            out["recoverable"] = True
            return out
        out["category"] = "synthesis_failure"
        return out

    return out

