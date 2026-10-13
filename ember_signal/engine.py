"""
Subprocess adapter to the ember-lite engine.

Why a subprocess and not an import: ember-lite ships no pyproject/setup.py, so it
cannot be `pip install`ed. It also owns SQLite databases and Ed25519 keys that
must stay single-writer. Running one short-lived interpreter per request keeps
ember-signal stateless and leaves all engine state with the engine.

Configuration (environment):
  EMBER_LITE_DIR       path to an ember-lite checkout (default /opt/ember-lite)
  EMBER_LITE_PYTHON    interpreter that has ember-lite's deps (default: this one)
  EMBER_ENGINE_TIMEOUT seconds before a call is abandoned (default 30)
"""

import json
import os
import subprocess
import sys

DEFAULT_ENGINE_DIR = "/opt/ember-lite"
DEFAULT_TIMEOUT = 30

# Each operation runs inside ember-lite with cwd set to the engine dir. The body
# must assign `result`; the wrapper prints {"ok": true, "data": result}.
_SCRIPT_TEMPLATE = """\
import json

def _run():
{body}
    return result

try:
    print(json.dumps({{"ok": True, "data": _run()}}))
except Exception as exc:
    print(json.dumps({{"ok": False, "error": type(exc).__name__, "detail": str(exc)}}))
    raise SystemExit(3)
"""

_OPERATIONS = {
    "chain": """
    from perception.evidence_chain import get_chain_summary, verify_chain
    result = {"summary": get_chain_summary(), "verify": verify_chain()}
""",
    "perceive": """
    from perception.layer import perceive, perceive_summary
    report = perceive(save=False)
    result = {"report": report, "summary": perceive_summary(report)}
""",
    # perceive() reaches the network; when it fails the gate still runs and
    # reports the affected dimensions as UNKNOWN rather than guessing.
    "gate": """
    report = None
    try:
        from perception.layer import perceive
        report = perceive(save=False)
    except Exception:
        report = None
    from perception.release_gate import evaluate_release, format_gate_report
    evaluation = evaluate_release(report)
    result = {"evaluation": evaluation, "report": format_gate_report(evaluation)}
""",
    "govern": """
    from perception.governance import get_governance_summary
    result = get_governance_summary()
""",
}


class EngineError(Exception):
    """The engine ran but the requested operation failed."""

    kind = "engine_error"

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class EngineUnavailable(EngineError):
    """The engine could not be reached at all."""

    kind = "engine_unavailable"


def _engine_dir() -> str:
    path = os.environ.get("EMBER_LITE_DIR", DEFAULT_ENGINE_DIR)
    if not os.path.isdir(path):
        raise EngineUnavailable(f"engine directory not found: {path}")
    return path


def _interpreter() -> str:
    return os.environ.get("EMBER_LITE_PYTHON", sys.executable)


def _timeout() -> int:
    try:
        return int(os.environ.get("EMBER_ENGINE_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


def engine_status() -> dict:
    """Non-throwing probe used by /api/health."""
    path = os.environ.get("EMBER_LITE_DIR", DEFAULT_ENGINE_DIR)
    return {
        "configured_dir": path,
        "available": os.path.isdir(path),
        "interpreter": _interpreter(),
    }


def run_operation(name: str) -> dict:
    """
    Run a named engine operation and return its data.

    Raises EngineUnavailable when the engine cannot be reached, or EngineError
    when it runs but the operation fails. Never returns fabricated data.
    """
    body = _OPERATIONS.get(name)
    if body is None:
        raise EngineError(f"unknown operation: {name}")

    engine_dir = _engine_dir()
    script = _SCRIPT_TEMPLATE.format(body=body)

    env = dict(os.environ)
    env["PYTHONPATH"] = engine_dir + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.run(
            [_interpreter(), "-c", script],
            cwd=engine_dir,
            capture_output=True,
            text=True,
            timeout=_timeout(),
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise EngineUnavailable(f"engine timed out after {_timeout()}s")
    except OSError as exc:
        raise EngineUnavailable(f"could not launch engine interpreter: {exc}")

    envelope = _parse_envelope(proc)
    if envelope.get("ok"):
        return envelope["data"]
    raise EngineError(
        f"{envelope.get('error', 'EngineError')}: {envelope.get('detail', '')}".strip()
    )


def _parse_envelope(proc: subprocess.CompletedProcess) -> dict:
    stdout = (proc.stdout or "").strip()
    if not stdout:
        detail = (proc.stderr or "").strip().splitlines()
        raise EngineUnavailable(
            "engine produced no output" + (f": {detail[-1]}" if detail else "")
        )
    try:
        envelope = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError:
        raise EngineUnavailable(f"engine output was not JSON: {stdout[:200]!r}")
    if not isinstance(envelope, dict) or "ok" not in envelope:
        raise EngineUnavailable("engine output missing envelope")
    return envelope
