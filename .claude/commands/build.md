---
description: 写 build 脚本产出两个 JSON 并生成单文件 HTML 看板
---

把抽取好的内容规整成契约 JSON 并生成页面。字段定义见 `docs/DATA_CONTRACT.md`。

1. 没把握契约长什么样，先跑 `python3 demo/make_demo.py` 打开产物看一眼，比读文档快。
2. `cp starter/build_assets.py starter/build_data.py workspace/`，照着改。
3. 两个最容易做错的地方：
   - **参考区间逐次测量存**（`vals[].lo/hi/ref`），不是只存项目级。
   - `threads` / `grades` **只摘录报告原文**，不推断病情、不给医学建议。
4. 生成：
   ```bash
   cd workspace && python3 build_assets.py && python3 build_data.py && cd ..
   python3 build_html.py workspace/out/我的健康档案.html \
           --data workspace/data.json --assets workspace/assets.json
   ```
5. 接着跑 `/verify`。**产物不要 commit、不要发到任何地方。**

$ARGUMENTS
