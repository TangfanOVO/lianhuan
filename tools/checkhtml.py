#!/usr/bin/env python3
"""清洗那份大界面时的安全网：每改一刀就验一次。

验三样：① 每个 <script> 块的 JS 语法 ② 主要标签是否平衡 ③ 关键结构还在不在。
"""
import re, subprocess, sys, tempfile, os

f = sys.argv[1] if len(sys.argv) > 1 else 'app/index.html'
s = open(f, encoding='utf-8').read()
bad = []

# ① JS 语法（跳过 importmap / module 之外的都验）
for i, m in enumerate(re.finditer(r'<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>', s, re.S)):
    attrs, body = m.group(1), m.group(2)
    if 'importmap' in attrs or not body.strip():
        continue
    with tempfile.NamedTemporaryFile('w', suffix='.mjs' if 'module' in attrs else '.js',
                                     delete=False, encoding='utf-8') as t:
        t.write(body); path = t.name
    r = subprocess.run(['node', '--check', path], capture_output=True, text=True)
    os.unlink(path)
    if r.returncode:
        line = s[:m.start(2)].count('\n') + 1
        bad.append(f"script#{i}（第 {line} 行起）JS 语法炸了：{r.stderr.strip().splitlines()[-3:] if r.stderr else ''}")

# ② 标签平衡（只看容易删坏的几种）
for tag in ('div', 'section', 'button', 'script', 'style', 'svg'):
    o = len(re.findall(rf'<{tag}[\s>]', s))
    c = len(re.findall(rf'</{tag}>', s))
    if o != c:
        bad.append(f"<{tag}> 不平衡：开 {o} 闭 {c}")

# ③ 关键结构
for need in ('id="app"', 'id="p-chat"', 'id="p-home"', '<meta charset="utf-8">'):
    if need not in s:
        bad.append(f"关键结构没了：{need}")

if bad:
    print("✗ " + "\n✗ ".join(bad)); sys.exit(1)
print(f"✓ 结构完好 · {len(s.splitlines())} 行 · {len(s)} 字节")
