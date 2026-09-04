"""一个**真的** HTTP 上游，冒充 Anthropic —— 用来在没有 key 的情况下把整条路走通。

★ 它跟 tests/ 里那个假上游不是一回事：那个是进程内替掉 httpx，这个是真的
  监听端口、真的收 TCP、真的解 HTTP 头、真的回 JSON。连环那头一个字都不知道
  自己在跟谁说话 —— 走的是同一份代码、同一个 httpx、同一套鉴权头。

★ 唯一不真的：它不是 Anthropic。所以它能证明「我们发得对、解得对、界面接得住」，
  证明不了「Anthropic 真的这么回」。响应形状照 platform.claude.com/docs/en/api/models-list
  抄的（data / id / display_name / type / created_at / has_more）。
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

KEY = "sk-ant-fake-for-local-test"

MODELS = [
    ("claude-opus-5",     "Claude Opus 5"),
    ("claude-sonnet-5",   "Claude Sonnet 5"),
    ("claude-fable-5-1",  "Claude Fable 5.1"),
    ("claude-opus-4-8",   "Claude Opus 4.8"),
    ("claude-opus-4-7",   "Claude Opus 4.7"),
    ("claude-opus-4-6",   "Claude Opus 4.6"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
]
KNOWN = {m[0] for m in MODELS}
SEEN = []          # 记下每一次请求，验完拿出来看


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        """照真的来：没有 x-api-key 就 401，跟 api.anthropic.com 一个说法。"""
        if self.headers.get("x-api-key") != KEY:
            self._send(401, {"type": "error", "error": {
                "type": "authentication_error", "message": "x-api-key header is required"}})
            return False
        if not self.headers.get("anthropic-version"):
            self._send(400, {"type": "error", "error": {
                "type": "invalid_request_error", "message": "anthropic-version header is required"}})
            return False
        return True

    def do_GET(self):
        SEEN.append({"m": "GET", "path": self.path, "h": dict(self.headers)})
        if not self.path.startswith("/v1/models"):
            self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})
            return
        if not self._auth():
            return
        self._send(200, {
            "data": [{"id": i, "display_name": n, "type": "model",
                      "created_at": "2026-07-24T00:00:00Z"} for i, n in MODELS],
            "first_id": MODELS[0][0], "last_id": MODELS[-1][0], "has_more": False})

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append({"m": "POST", "path": self.path, "h": dict(self.headers), "body": body})
        if not self._auth():
            return
        model = body.get("model") or ""
        # ★ 关键的一条：模型名打错了，真的 Anthropic 回的就是 404 + not_found_error
        if model not in KNOWN:
            self._send(404, {"type": "error", "error": {
                "type": "not_found_error", "message": f"model: {model}"}})
            return
        if body.get("stream"):
            lines = [
                {"type": "message_start", "message": {"usage": {
                    "input_tokens": 137, "cache_read_input_tokens": 8800,
                    "cache_creation_input_tokens": 1600}}},
                {"type": "content_block_delta", "delta": {
                    "type": "text_delta", "text": f"在。（这句是 {model} 说的）"}},
                {"type": "message_delta", "usage": {"output_tokens": 29}},
                {"type": "message_stop"},
            ]
            payload = "".join("event: x\ndata: " + json.dumps(e, ensure_ascii=False) + "\n\n"
                              for e in lines).encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._send(200, {"stop_reason": "end_turn",
                         "content": [{"type": "text", "text": f"在。（{model}）"}],
                         "usage": {"input_tokens": 137, "output_tokens": 29}})


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8455
    print(f"假上游起在 {port}，key = {KEY}")
    HTTPServer(("127.0.0.1", port), H).serve_forever()
