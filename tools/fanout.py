#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 3, and strictly optional: read many page images in parallel subprocesses.

    python3 tools/fanout.py --check                     # which CLI, if any, is usable
    python3 tools/fanout.py workspace/raw/pages/*.png   # one JSON per page → stdout
    python3 tools/fanout.py --batch 4 --out workspace/raw/extracted.json  ...

Only reach for this when layer 2 does not fit — dozens of reports, hundreds of pages,
more than one context can hold. It shells out to whichever agent CLI happens to be on
the machine (`claude -p` or `codex exec`), asking each subprocess to read a few page
images and return JSON.

NOTHING HERE IS A DEPENDENCY. This repo must work under any agent tool, so if no CLI is
found the script says so and tells the caller to go back to layer 2 in batches. That is
a supported outcome, not a failure — never rewrite this into a hard requirement.
"""
import argparse, glob, json, os, shlex, shutil, subprocess, sys

PROMPT = """你在读一份体检/检验报告的页面图片。请逐张读，输出**一个 JSON 对象**，不要有任何其它文字。

格式：
{"pages":[{"file":"<文件名>","date":"YYYY-MM-DD","exam":"检查名称","type":"检验报告|超声报告|放射报告|心电报告|内镜报告",
  "items":[{"name":"项目名","text":"结果原样文本","unit":"单位","ref":"参考区间原文","flag":"H|L|A|null"}],
  "findings":"检查所见原文（影像类才有）","conclusion":"诊断结论原文","unsure":["读不清的项目名"]}]}

规则：
- 只抄写页面上印着的内容，**不要推断、不要补全、不要做任何医学判断**。
- flag 用报告自己印的 ↑↓ 或异常标记；报告没标就填 null，**不要自己按区间算**。
- 参考区间照抄原文（如 "12.3-107.0"、"≥50"、"阴性"），不要归一化。
- 看不清的项目**不要猜**，把项目名放进 unsure，text 填 ""。

要读的文件："""

RUNNERS = [
    # (binary, argv-builder)  — first one present on PATH wins.
    ('claude', lambda prompt: ['claude', '-p', prompt]),
    ('codex', lambda prompt: ['codex', 'exec', prompt]),
]


def detect():
    return [(name, build) for name, build in RUNNERS if shutil.which(name)]


def run_batch(build, files, timeout):
    prompt = PROMPT + '\n' + '\n'.join(os.path.abspath(f) for f in files)
    try:
        p = subprocess.run(build(prompt), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f'超时（{timeout}s）'
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'
    if p.returncode != 0:
        return None, (p.stderr or p.stdout or '').strip()[:200]
    out = p.stdout.strip()
    start, end = out.find('{'), out.rfind('}')       # CLIs like to wrap JSON in prose
    if start < 0 or end < start:
        return None, 'no JSON in output'
    try:
        return json.loads(out[start:end + 1]), None
    except json.JSONDecodeError as e:
        return None, f'bad JSON: {e}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*', help='页面图片（支持通配符展开后的列表）')
    ap.add_argument('--check', action='store_true', help='只报告有没有可用的 CLI')
    ap.add_argument('--batch', type=int, default=4, help='每个子进程读几张（默认 4）')
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--out', default=None, help='汇总写到这个 JSON 文件')
    a = ap.parse_args()

    found = detect()
    if a.check or not a.files:
        if found:
            print('可用：' + '、'.join(n for n, _ in found))
            print(f'用法：python3 tools/fanout.py --batch {a.batch} '
                  'workspace/raw/pages/*.png --out workspace/raw/extracted.json')
        else:
            print('没有找到 claude 或 codex。')
            print('这不是错误——回到第 2 层就行：把页面图片分几批，'
                  '你自己用 Read 逐张打开读，读完再汇总。')
        return 0 if a.files or a.check else 1

    files = [f for pat in a.files for f in (glob.glob(pat) if '*' in pat else [pat])]
    files = [f for f in files if os.path.exists(f)]
    if not files:
        sys.exit('没有匹配到任何文件')
    if not found:
        print(f'没有可用的 CLI，但你有 {len(files)} 张图要读。', file=sys.stderr)
        print('回到第 2 层：分批用 Read 打开这些图自己读。文件列表：', file=sys.stderr)
        for f in files:
            print(' ', f, file=sys.stderr)
        return 1

    name, build = found[0]
    batches = [files[i:i + a.batch] for i in range(0, len(files), a.batch)]
    print(f'用 {name} 处理 {len(files)} 张图，分 {len(batches)} 批', file=sys.stderr)

    pages, failed = [], []
    for i, batch in enumerate(batches, 1):
        got, err = run_batch(build, batch, a.timeout)
        if err:
            print(f'  批次 {i}/{len(batches)} 失败：{err}', file=sys.stderr)
            failed.extend(batch)
            continue
        pages.extend(got.get('pages', []))
        print(f'  批次 {i}/{len(batches)} ✓ {len(got.get("pages", []))} 页', file=sys.stderr)

    result = {'pages': pages, 'failed': failed}
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as fh:
            fh.write(text)
        print(f'{len(pages)} 页 → {a.out}', file=sys.stderr)
    else:
        print(text)

    if failed:
        print(f'\n⚠ {len(failed)} 张没处理成功，请自己用 Read 打开补上：', file=sys.stderr)
        for f in failed:
            print(' ', f, file=sys.stderr)
    unsure = [(p.get('file'), p['unsure']) for p in pages if p.get('unsure')]
    if unsure:
        print(f'\n⚠ 子进程标了 {sum(len(u) for _, u in unsure)} 个读不清的项目，'
              '请自己看一眼原图确认——不要直接采信：', file=sys.stderr)
        for f, u in unsure:
            print(f'  {f}: {"、".join(u)}', file=sys.stderr)
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
