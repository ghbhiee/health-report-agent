---
description: 勘探 workspace/inbox 并把报告内容抽取成结构化数据
---

把 `workspace/inbox/` 里的原始数据抽成结构化内容。读 `docs/20-extract.md` 再动手。

1. `python3 tools/probe.py workspace/inbox` —— 看每份文件有没有文字层、几页、几张图。
2. 分两层处理：
   - **有文字层** → `python3 tools/extract.py text <file>`，直接拿全文，零误差。
   - **没有文字层** → `python3 tools/extract.py pages <file>` 渲染成 PNG，
     然后**你自己用 Read 打开图片读**。不要去找 OCR 引擎，你就是最好的那个。
3. 量大到撑爆上下文时才考虑 `python3 tools/fanout.py`（可选，探测 claude/codex）。
4. 对照 `docs/20-extract.md` 的 9 个数据坑逐条排查——几乎每份数据都会中几条。
5. **异常值必须复读一次**再定稿。读不清的标「待核对」告诉用户，不要猜。

$ARGUMENTS
