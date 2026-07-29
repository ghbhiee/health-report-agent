---
description: 校验产物：契约合规、引用完整、零外链、偏离标记交叉校验 + 浏览器验收
---

验收生成好的健康档案。**脚本过了不算完，必须在浏览器里真的点一遍。**

1. 跑校验：
   ```bash
   python3 tools/verify.py workspace/data.json workspace/assets.json \
           workspace/out/我的健康档案.html
   ```
   它查：契约字段、`sources[].no` 引用完整性、**产物零外链零 fetch**、
   以及**交叉校验**——你按参考区间自己算的偏离标记 vs 报告上印的 ↑↓。
2. **交叉校验不一致时不要改数**。列出来交给用户核对，说明哪一侧可能有问题。
3. 打开 `docs/30-build-verify.md`，**按清单在浏览器里逐条过**。
   重点是分屏弹窗、抽屉滚动、来源报告高亮、灯箱翻页、深浅色——这几条踩过坑。
4. 把「哪些数据核对过、哪些没有」写进 `data.json` 的 `footNotes`，用户才知道能信到什么程度。

$ARGUMENTS
