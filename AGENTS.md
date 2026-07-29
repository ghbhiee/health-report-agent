# AGENTS.md — 给 agent 的操作手册

你是被用户请来的助手。用户把这个目录交给你，是想要**一个双击就能打开的单文件 HTML 健康看板**：
把他散落各处的体检 / 检验 / 影像报告收拢、抽取、汇成一页，化验能看趋势、影像图能翻、
PDF 原件内嵌可查。**全程本地，不上传任何数据。**

**这份东西不只是自己存档，很大程度上是为了「带去给医生看」**——诊室时间很短，医生想知道的
通常是趋势而不是单次数值。所以你做的时候优先保证三件事：**趋势看得清**（多年折线 + 参考区间）、
**原件翻得到**（医生要核对时能立刻点开 PDF）、**带得走**（单文件、离线可开）。

先读完这一页再动手。细节文档在 `docs/`，用到哪份看哪份。

> **用户是第一次用？** 直接走 `/onboarding`——它会一步一停地带他从「先看演示」到「拿到自己的看板」，比你自由发挥更稳。

---

## 0. 心智模型（先建立这个，其余都是细节）

```
   原始数据（PDF / 截图 / 照片 / 压缩包 / 录屏…）
        │  ← 每个人的数据都不一样，这一段要动脑：你写 build_assets.py + build_data.py
        ▼
   data.json  +  assets.json          ← 契约，见 docs/DATA_CONTRACT.md
        │  ← build_html.py，纯机械替换，你永远不用改它
        ▼
   我的健康档案.html                   ← 模板 template/app_template.html，功能已固化
```

**关键认识**：页面的全部功能——5 个视图、趋势图、报告抽屉、影像灯箱、批次对比、深浅色——
都写死在模板里、已充分测试。**你几乎不碰模板**。
你的全部工作是把千奇百怪的原始数据**规整成契约里那三个 JSON**。

不确定契约长什么样时，别读文档——直接跑一遍 demo 看产物：

```bash
python3 demo/make_demo.py && python3 -m webbrowser -t demo/index.html
```

---

## 1. 四步流程

| 步 | 做什么 | 看哪份文档 |
|---|---|---|
| ① 取数 | 问清用户数据在哪，引导他拿到手 → 落到 `workspace/inbox/` | `docs/1x-acquire-*.md` |
| ② 勘探 + 抽取 | 摸清数据形态，把内容读成结构化数据 | `docs/20-extract.md` |
| ③ 生成 | 写 `build_assets.py` / `build_data.py` → 跑 `build_html.py` | `docs/DATA_CONTRACT.md` |
| ④ 验收 | 校验脚本 + **浏览器里真的过一遍** | `docs/30-build-verify.md` |

### ① 取数：先问，别猜

用户一上来通常只说"帮我做个健康档案"。**你要主动问他数据在哪**，给他这三个选项：

> 你的体检 / 检查报告现在在哪？
> 1. **我手里已经有 PDF 或照片了** —— 最省事，直接放进来就行
> 2. **在医院或体检机构的网站上，我能用电脑登录** —— 我可以引导你用浏览器批量下载
> 3. **只在微信 / 支付宝小程序里** —— 用电脑版微信打开小程序，把报告链接转到 Chrome

对应文档：

- 选 1 → `docs/12-acquire-manual.md`（**兜底路线，覆盖面最广，拿不准就先走这条**）
- 选 2 → `docs/10-acquire-browser.md`
- 选 3 → `docs/11-acquire-mobile.md`（小程序**不要试图驱动**，那份文档讲了为什么）

用户可能几种混着来（PDF 一部分、手机截图一部分），这很正常，分别处理即可。

### ② 勘探 + 抽取：**先勘探，别急着写解析**

```bash
python3 tools/probe.py workspace/inbox      # 每份文件是什么、有没有文字层、有几张图
```

`probe.py` 会把文件分成两拨，这决定你怎么抽：

- **有文字层的 PDF** → `python3 tools/extract.py text <file>` 直接拿全文，零误差。
  真实数据里 CT / MR / 超声 / 内镜报告大多属于这类，是大头。
- **没有文字层**（扫描件 / 手机照片 / 长截图 / 视频抽帧）→
  `python3 tools/extract.py pages <file>` 渲染成 PNG，然后**你自己用 `Read` 打开图片读**。
  你是多模态模型，看化验单比任何 OCR 引擎都准。**本项目不需要安装任何 OCR 引擎。**

量大到撑爆上下文时（几十份报告），可选地用 `tools/fanout.py` 起子进程分批处理——
它会自己探测 `claude` / `codex` 谁可用；都没有就直接告诉你，由你分批读。**不要把任何 CLI 当成前提**。

抽取时对照 `docs/20-extract.md` 里那 **9 个反复出现的数据坑**排查，几乎每份数据都会中招几条。

### ③ 生成

从 `starter/` 复制两个骨架脚本到 `workspace/`，照着改：

```bash
cp starter/build_assets.py starter/build_data.py workspace/
# 改完后：
cd workspace && python3 build_assets.py && python3 build_data.py
python3 ../build_html.py 我的健康档案.html --data data.json --assets assets.json
```

字段定义看 `docs/DATA_CONTRACT.md`。有两条**最容易做错**，先记住：

- **参考区间要逐次测量存**（`vals[].lo/hi/ref`），不是只存项目级——实验室会改判读标准，
  只存一个区间会把正常值误判成偏高。这是踩过的真实坑。
- `threads`（健康主线）和 `grades`（结节分级随访）**必须逐条对应报告原文**，
  只做摘录、不做推断。见下面的红线。

### ④ 验收

```bash
python3 tools/verify.py workspace/data.json workspace/assets.json workspace/我的健康档案.html
```

它查契约合规、引用完整性、**产物零外链**，以及**交叉校验**：
你按参考区间自己算出的偏离标记，必须和报告上印的 ↑↓ 一致，不一致会列出来。
**不一致时不要自作主张改数**——列给用户看，让他核对。

脚本过了**还不算完**。必须**在浏览器里真的点一遍**，清单在 `docs/30-build-verify.md`。

---

## 2. 红线（不可协商）

1. **用户数据只留本地**。所有原始文件和产物一律放 `workspace/`（已被 `.gitignore` 排除）。
   **永远不要 `git add` 用户数据，不要 commit 产物 HTML，不要把它发到任何地方**——
   不发 Artifact、不发图床、不发邮件、不上传任何服务。这是个人健康数据。
2. **不做医学诊断**。页面只是把已有报告**重新组织展示**。
   结论、分级、随访建议一律**摘录报告原文**，不要由你推断病情、不要给医学建议。
   模板页脚的免责声明**必须保留**（它写死在模板里，不要删）。
3. **绝不代用户输入账号、密码、短信验证码**。取数时只在**用户已经自己登录好**的页面上
   做导航和下载。这条没有例外。
4. **产物必须零外链零 fetch**。模板已满足；你若改了模板，`tools/verify.py` 会重新检查。
5. **不确定的数字不要编**。读不清就标注"待核对"并告诉用户，不要猜一个像样的值填进去。

---

## 3. 目录

```
AGENTS.md            ← 本文件
docs/                ← 分步文档，按需读
  00-overview.md       整体流程与心智模型（本文件的展开版）
  10-acquire-browser.md  路线①：电脑浏览器从医疗平台批量下载
  11-acquire-mobile.md   路线②：手机小程序 → 把链接转到电脑
  12-acquire-manual.md   路线③：已有 PDF / 照片 / 录屏（兜底，覆盖最广）
  20-extract.md          勘探、三层抽取、9 个数据坑、核对方法
  30-build-verify.md     生成与浏览器验收清单
  DATA_CONTRACT.md       三个 JSON 的精确字段定义
template/app_template.html   页面本体（黑盒，一般不改）
build_html.py                data+assets → 单文件 html（不用改）
tools/  lib.py probe.py extract.py fanout.py verify.py scan_privacy.py
starter/  build_assets.py build_data.py    ← 复制到 workspace/ 改
demo/     make_demo.py + 合成演示数据（全部虚构）
workspace/  ← 用户数据放这里，已 gitignore
  inbox/  原始文件丢这
  raw/    解压 / 渲染出来的中间产物
  out/    产物 HTML
```

## 4. 依赖

```bash
pip install -r requirements.txt      # pymupdf pillow numpy openpyxl
```

纯 Python，Python 3.9+，macOS / Linux / Windows 都能跑。**不需要 OCR 引擎、不需要任何 CLI**。

---

## 5. 一页速查

```bash
python3 demo/make_demo.py && python3 -m webbrowser -t demo/index.html      # 先看效果，理解契约
python3 tools/probe.py workspace/inbox                 # 勘探
python3 tools/extract.py text  workspace/inbox/x.pdf   # 有文字层：直接取
python3 tools/extract.py pages workspace/inbox/x.pdf   # 没文字层：渲染成图，你自己读
cp starter/build_*.py workspace/                       # 抄骨架开写
python3 build_html.py workspace/out/我的健康档案.html \
        --data workspace/data.json --assets workspace/assets.json
python3 tools/verify.py workspace/data.json workspace/assets.json workspace/out/我的健康档案.html
```
