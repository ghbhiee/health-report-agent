---
description: 引导用户把体检/检查报告弄到 workspace/inbox/
---

帮用户把报告数据收集到 `workspace/inbox/`。

1. 先问清楚数据在哪，给他这三个选项（别替他猜）：
   1. 手里已有 PDF / 照片 → 读 `docs/12-acquire-manual.md`
   2. 能在电脑上登录医院或体检机构网站 → 读 `docs/10-acquire-browser.md`
   3. 只在手机微信 / 支付宝小程序里 → 读 `docs/11-acquire-mobile.md`
2. 按对应文档执行。几种混着来很正常，分别处理。
3. **红线：绝不代用户输入账号、密码、验证码。** 只在他已登录好的页面上做导航和下载。
4. 收完跑 `python3 tools/probe.py workspace/inbox`，把勘探结果讲给用户听。

$ARGUMENTS
