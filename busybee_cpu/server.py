from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from busybee_cpu.policy import CpuActionPolicy


def strict_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def parse_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    combined = "\n".join(str(message.get("content") or "") for message in messages)
    parsed = extract_json_object(combined)
    if parsed and ("state" in parsed or "goal" in parsed):
        return parsed
    return {"goal": combined, "state": {"recent_observations": [combined]}, "available_tools": []}


class PolicyServer(ThreadingHTTPServer):
    policy: CpuActionPolicy
    exposed_model: str


class Handler(BaseHTTPRequestHandler):
    server: PolicyServer

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"ok": True, "model": self.server.exposed_model})
            return
        if self.path == "/v1/models":
            self.send_json(200, {"object": "list", "data": [{"id": self.server.exposed_model, "object": "model", "created": 0, "owned_by": "busybee-cpu"}]})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        row = parse_messages(request.get("messages") or [])
        action = self.server.policy.predict(row)
        content = strict_json(action)
        self.send_json(
            200,
            {
                "id": "chatcmpl-busybee-cpu",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.server.exposed_model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a CPU action policy through an OpenAI-compatible endpoint.")
    parser.add_argument("--model", required=True, help="Path to a trained joblib policy.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--exposed-model", default="busybee-cpu")
    args = parser.parse_args()

    server = PolicyServer((args.host, args.port), Handler)
    server.policy = CpuActionPolicy.load(args.model)
    server.exposed_model = args.exposed_model
    print(f"BusyBee CPU server listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
