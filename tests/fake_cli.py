#!/usr/bin/env python3
"""假的 CLI —— 只为测解析逻辑，不接任何模型。

吐一段跟真 CLI 一样格式的 stream-json，包括几个**故意的杂质**：
横幅行、坏 JSON 行 —— 真 CLI 会吐这些，解析器必须跳过而不是炸掉。

用法：FAKE_MODE=silent 就一个字都不说（测「一个字都没说出来」那条路）。
"""
import json
import os
import sys

print("Some banner line that is not JSON")          # 杂质①：横幅
print("{ this is broken json")                       # 杂质②：坏 JSON

emit = lambda d: print(json.dumps(d, ensure_ascii=False), flush=True)
emit({"type": "system", "subtype": "init", "session_id": "sess-abc123"})

if os.environ.get("FAKE_MODE") != "silent":
    emit({"type": "stream_event", "event": {"type": "content_block_delta",
          "delta": {"type": "thinking_delta", "thinking": "先想一下。"}}})
    emit({"type": "stream_event", "event": {"type": "content_block_start",
          "content_block": {"type": "tool_use", "name": "Read"}}})
    for chunk in ["第一句。", "|||", "第二句", "还是第二句。", "|||", "最后一句没有记号"]:
        emit({"type": "stream_event", "event": {"type": "content_block_delta",
              "delta": {"type": "text_delta", "text": chunk}}})

emit({"type": "result", "session_id": "sess-abc123"})
