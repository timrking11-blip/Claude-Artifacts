"""Guard: the ledger tools must import with nothing but the standard library.

The README and the composition page promise that the ledger tools run without
ADK, credentials or network -- and the repo's CI relies on it. A fresh
interpreter is used so a previously imported google.adk cannot mask a regression.
"""

import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]

PROBE = """
import sys
sys.path.insert(0, %r)
import account_research.tools.ledger
import account_research.tools.store_state  # noqa: F401 -- type-only ADK use
leaked = sorted(m for m in sys.modules if m == "google.adk" or m.startswith("google.adk."))
anthropic = [m for m in sys.modules if m == "anthropic" or m.startswith("anthropic.")]
print("ADK:", leaked)
print("ANTHROPIC:", anthropic)
""" % str(AGENT_DIR)


def test_ledger_tools_import_without_adk_or_anthropic():
    out = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "ADK: []" in out.stdout, out.stdout
    assert "ANTHROPIC: []" in out.stdout, out.stdout
