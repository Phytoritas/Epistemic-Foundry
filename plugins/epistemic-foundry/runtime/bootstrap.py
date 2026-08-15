"""Entry point for the plugin-resident Python runtime.

The installed plugin does not require an ``efoundry`` executable on PATH and
does not import the development checkout.  It carries its own copy of the
application package under ``runtime/python`` and runs it with an explicitly
constructed import path.

The launcher invokes this file as::

    <interpreter> -I <plugin-root>/runtime/bootstrap.py <cli args>

``-I`` isolates the interpreter: user site-packages, ``PYTHONPATH`` and
``PYTHONHOME`` are ignored.  That is deliberate.  A runtime that silently
resolved a different copy of ``epistemic_foundry`` would report facts about
bytes nobody chose.
"""

from __future__ import annotations

import json
import io
import sys
from pathlib import Path

#: Exit status for a bootstrap failure that never reached the application.
#: It must differ from every application outcome code (0/10/20/30/40/50/60/70/80)
#: and from the T01 CLI error table, so a launcher can tell "the runtime could
#: not start" apart from "the command ran and failed".
BOOTSTRAP_FAILURE = 71

RUNTIME_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = RUNTIME_ROOT / "python"
MANIFEST_PATH = RUNTIME_ROOT / "runtime-manifest.json"


def _force_utf8_streams() -> None:
    """Emit UTF-8 regardless of the host console code page.

    The CLI writes JSON containing non-ASCII text.  Under ``-I`` the
    interpreter ignores ``PYTHONUTF8`` and ``PYTHONIOENCODING``, so on a
    Windows console it would default to the legacy code page and raise
    ``UnicodeEncodeError`` on the first em dash.  Isolation is worth keeping,
    so the streams are reconfigured here instead.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
            continue
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            setattr(
                sys,
                stream_name,
                io.TextIOWrapper(
                    buffer, encoding="utf-8", errors="backslashreplace"
                ),
            )


def _fail(code: str, message: str) -> "int":
    """Report a bootstrap failure as one JSON object on stderr."""
    payload = {
        "error_code": code,
        "message": message,
        "runtime_root": str(RUNTIME_ROOT),
        "status": "BOOTSTRAP_FAILED",
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return BOOTSTRAP_FAILURE


def main(argv: list[str]) -> int:
    _force_utf8_streams()
    if sys.version_info < (3, 11):
        return _fail(
            "PYTHON_VERSION_UNSUPPORTED",
            "the bundled runtime requires Python 3.11 or newer, "
            f"found {sys.version_info.major}.{sys.version_info.minor}",
        )
    if not PACKAGE_ROOT.is_dir():
        return _fail(
            "RUNTIME_INTEGRITY_FAILED",
            f"the bundled package root is missing at {PACKAGE_ROOT}",
        )
    if not MANIFEST_PATH.is_file():
        return _fail(
            "RUNTIME_INTEGRITY_FAILED",
            f"the runtime manifest is missing at {MANIFEST_PATH}",
        )

    # The bundled tree is the only place the application may come from, so it
    # goes at the front and nothing else is added.
    sys.path.insert(0, str(PACKAGE_ROOT))

    try:
        from epistemic_foundry.cli.main import main as cli_main
    except Exception as exc:  # noqa: BLE001 - reported verbatim to the caller
        return _fail(
            "BUNDLED_IMPORT_FAILED",
            f"the bundled epistemic_foundry package failed to import: {exc}",
        )

    resolved = Path(getattr(sys.modules["epistemic_foundry"], "__file__", ""))
    try:
        resolved.relative_to(PACKAGE_ROOT)
    except ValueError:
        return _fail(
            "BUNDLED_IMPORT_FAILED",
            "epistemic_foundry resolved outside the bundled runtime: "
            f"{resolved}",
        )

    # `main` takes argv explicitly, so the arguments are passed rather than
    # written into `sys.argv`; `prog` is still set for help and error text.
    sys.argv[0] = "efoundry"
    return int(cli_main(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise SystemExit(BOOTSTRAP_FAILURE)
