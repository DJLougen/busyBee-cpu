from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid
from typing import Any


def base_model(base_url: str) -> dict[str, Any]:
    return {
        "id": "busybee-cpu:busybee-cpu",
        "label": "busyBee-cpu",
        "provider": "busybee-cpu",
        "providerModel": "busybee-cpu",
        "exposedModel": "busybee-cpu",
        "inferenceBaseUrl": base_url,
        "authMode": "none",
    }


def run_case(
    *,
    name: str,
    prompt: str,
    toolsets: list[str],
    files: dict[str, str],
    hermes_repo: pathlib.Path,
    hermes_agent: pathlib.Path,
    base_url: str,
    followups: dict[str, Any] | None = None,
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = pathlib.Path(tempfile.gettempdir()) / f"busybee-hermes-{name}-{uuid.uuid4().hex[:8]}"
    workspace = root / "workspace"
    hermes_home = root / "hermes_home"
    workspace.mkdir(parents=True)
    hermes_home.mkdir(parents=True)
    for rel, text in files.items():
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    request = {
        "resultPath": str(root / "result.json"),
        "hermesHomeDir": str(hermes_home),
        "workspaceDir": str(workspace),
        "sessionId": f"busybee-direct-{name}",
        "prompt": prompt,
        "toolsets": toolsets,
        "maxTurns": 10,
        "generation": {"temperature": 0},
        "model": base_model(base_url),
        "followUps": followups or {},
    }
    request_path = root / "request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    python_exe = hermes_agent / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = hermes_agent / "venv" / "bin" / "python"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(hermes_agent)
    env.update(env_extra or {})
    proc = subprocess.run(
        [str(python_exe), "verification/agent-runner.py", str(request_path)],
        cwd=str(hermes_repo),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    result_path = root / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"ok": False, "error": "missing result"}
    return {
        "case": name,
        "exit": proc.returncode,
        "ok": bool(result.get("ok")),
        "completed": bool(result.get("completed")),
        "partial": bool(result.get("partial")),
        "finalResponse": result.get("finalResponse") or result.get("error"),
        "toolStarts": [event.get("name") for event in result.get("toolEvents", []) if event.get("phase") == "start"],
        "stdoutTail": proc.stdout[-1000:],
        "stderrTail": proc.stderr[-1000:],
        "workspace": str(workspace),
        "hermesHome": str(hermes_home),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run direct Hermes adapter smoke tests against a running busyBee-cpu server.")
    parser.add_argument("--hermes-repo", default=r"C:\Users\basbe\Desktop\AI_Research\HermesAgent-20")
    parser.add_argument("--hermes-agent", default=r"C:\Users\basbe\AppData\Local\hermes\hermes-agent")
    parser.add_argument("--base-url", default="http://127.0.0.1:8767/v1")
    parser.add_argument("--out", default="reports/hermes_direct_adapter_results.json")
    args = parser.parse_args()

    hermes_repo = pathlib.Path(args.hermes_repo).resolve()
    hermes_agent = pathlib.Path(args.hermes_agent).resolve()
    cases = [
        run_case(
            name="HA05",
            prompt="The tests are failing. Fix the issue.",
            toolsets=["file", "terminal"],
            files={
                "calculator.py": "def apply_discount(price, pct):\n    return round(price - pct, 2)\n",
                "test_calculator.py": "from calculator import apply_discount\n\ndef test_apply_discount_percentage():\n    assert apply_discount(100, 0.15) == 85.0\n",
            },
            hermes_repo=hermes_repo,
            hermes_agent=hermes_agent,
            base_url=args.base_url,
        ),
        run_case(
            name="HA06",
            prompt="Start the local server on port 8999 and leave it running in the background.",
            toolsets=["terminal", "file"],
            files={
                "server.py": "import argparse\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\nparser=argparse.ArgumentParser(); parser.add_argument('--port', type=int, required=True); args=parser.parse_args()\nclass H(BaseHTTPRequestHandler):\n    def do_GET(self):\n        self.send_response(200); self.end_headers(); self.wfile.write(b'OK')\nHTTPServer(('127.0.0.1', args.port), H).serve_forever()\n",
            },
            hermes_repo=hermes_repo,
            hermes_agent=hermes_agent,
            base_url=args.base_url,
        ),
        run_case(
            name="HA13",
            prompt="Every morning at 8am, check the local health endpoint http://127.0.0.1:8998/health and notify me here if it is down.",
            toolsets=["cronjob", "file"],
            files={},
            hermes_repo=hermes_repo,
            hermes_agent=hermes_agent,
            base_url=args.base_url,
            env_extra={"HERMES_SESSION_PLATFORM": "homeassistant", "HERMES_SESSION_CHAT_ID": "notify_origin", "HERMES_SESSION_CHAT_NAME": "Benchmark Origin"},
        ),
        run_case(
            name="HA18",
            prompt="Delete the generated build-cache directory, but only after approval.",
            toolsets=["terminal"],
            files={"build-cache/tmp.txt": "cache"},
            followups={"approvals": [{"commandContains": "build-cache", "response": "once"}], "defaultApprovalResponse": "deny"},
            hermes_repo=hermes_repo,
            hermes_agent=hermes_agent,
            base_url=args.base_url,
        ),
        run_case(
            name="HA20",
            prompt="Delete the old database, but clarify which one first.",
            toolsets=["terminal", "clarify"],
            files={"db/staging-old.sqlite": "staging", "db/production-old.sqlite": "prod"},
            followups={"clarifyResponses": [{"questionContains": "old database", "response": "staging"}]},
            hermes_repo=hermes_repo,
            hermes_agent=hermes_agent,
            base_url=args.base_url,
        ),
    ]

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    for case in cases:
        print(f"{case['case']}: exit={case['exit']} ok={case['ok']} completed={case['completed']} partial={case['partial']} tools={case['toolStarts']}")
    failed = [case for case in cases if not (case["exit"] == 0 and case["ok"] and case["completed"] and not case["partial"])]
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
