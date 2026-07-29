#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check a built dashboard before handing it to the user.

    python3 tools/verify.py workspace/data.json workspace/assets.json out.html
    python3 tools/verify.py demo/data.json demo/assets.json demo/index.html

Four checks:

  1. 契约      required fields, types, and shapes from docs/DATA_CONTRACT.md
  2. 引用完整   every sources[].no, imgs[].k, tw[] and manifest page resolves to an asset
  3. 交叉校验   the deviation flag recomputed from each measurement's own lo/hi against
                the flag actually stored — which, if you filled `f` from the ↑↓ the lab
                printed, compares the lab's judgement with the range it printed
  4. 零外链     the output HTML makes no network request of any kind

Check 3 is the important one. The private kit this grew out of got its trust from OCRing
the paper sheets back and diffing them against the export — and that diff caught a real
defect: a lab changed one reference range between visits, the summary sheet squashed the
two ranges into one, and a normal value came out flagged high. Without a second source
to collide with, storing the range per measurement plus this cross-check is what replaces
it. A mismatch is NOT permission to edit the number — it means the report and the range
disagree, and a human has to look.

Exit code 0 clean, 1 problems found. Passing all four still does not mean you are done:
open the file in a browser and walk docs/30-build-verify.md.
"""
import argparse, json, os, re, sys

OK, BAD = '  ✓', '  ✗'
issues, notes = [], []


def fail(msg):
    issues.append(msg)


def note(msg):
    notes.append(msg)


# ------------------------------------------------------------------ 1. 契约
REQ_REPORT = ('no', 'date', 'name', 'type', 'conclusion', 'status', 'file')
REQ_ITEM = ('name', 'ref', 'vals', 'numeric')
REQ_VAL = ('d', 'v', 'f', 't', 'ref')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
STATUSES = {'异常', '正常', '见结论'}


def check_contract(data):
    if not isinstance(data.get('patient'), dict) or not data['patient'].get('name'):
        fail('data.patient.name 缺失')
    reports = data.get('reports')
    if not isinstance(reports, list) or not reports:
        fail('data.reports 缺失或为空')
        return
    nos = [r.get('no') for r in reports]
    for dup in {n for n in nos if nos.count(n) > 1}:
        fail(f'reports[].no 重复：{dup}')
    for r in reports:
        where = f"report {r.get('no', '?')}"
        for k in REQ_REPORT:
            if not r.get(k):
                fail(f'{where} 缺字段 {k}')
        if r.get('date') and not DATE.match(r['date']):
            fail(f"{where} date 不是 YYYY-MM-DD：{r['date']}")
        if r.get('status') not in STATUSES:
            fail(f"{where} status 应为 {'/'.join(STATUSES)}，实际 {r.get('status')!r}")

    for p in data.get('panels', []):
        where = f"panel {p.get('key', '?')}"
        for k in ('key', 'label', 'dates', 'items'):
            if k not in p:
                fail(f'{where} 缺字段 {k}')
        if p.get('numericCount') is None:
            fail(f'{where} 缺 numericCount（=0 时该面板按定性呈现）')
        for it in p.get('items', []):
            iw = f"{where} · {it.get('name', '?')}"
            for k in REQ_ITEM:
                if k not in it:
                    fail(f'{iw} 缺字段 {k}')
            for v in it.get('vals', []):
                for k in REQ_VAL:
                    if k not in v:
                        fail(f'{iw} 的一次测量缺字段 {k}')
                if v.get('d') and v['d'] not in p.get('dates', []):
                    fail(f"{iw} 的测量日期 {v['d']} 不在 panel.dates 里")
            if it.get('vals') and 'refVaries' in it:
                varies = len({v.get('ref') for v in it['vals']}) > 1
                if varies and not it['refVaries']:
                    fail(f'{iw} 各次参考区间不一致，但 refVaries 是 false '
                         f'（表格不会加 * 注释）')

    for g in data.get('grades', []):
        if not all(g.get(k) for k in ('date', 'sys', 'grade', 'what')):
            fail(f'grades 里有条目缺 date/sys/grade/what：{g}')
    for c in data.get('clusters', []):
        if not c.get('dates'):
            fail(f"cluster {c.get('id')} 没有 dates，对比分析会拿不到数据")


# ------------------------------------------------------------ 2. 引用完整性
def check_refs(data, assets, manifest):
    keys = set(assets)
    mans = {m.get('no') for m in manifest}
    for r in data.get('reports', []):
        w = f"report {r.get('no')}"
        for s in r.get('sources', []) or [{'no': r.get('no')}]:
            if f"pdf{s['no']}" not in keys:
                fail(f"{w} 的来源 {s['no']} 没有 ASSETS['pdf{s['no']}']，抽屉里下载不了原件")
            if s['no'] not in mans:
                fail(f"{w} 的来源 {s['no']} 不在 MANIFEST 里，看不到页面渲染图")
        for g in r.get('imgs', []):
            if g.get('k') not in keys:
                fail(f"{w} 引用了不存在的图片 {g.get('k')}")
        for t in r.get('tw', []):
            if t not in mans:
                fail(f'{w} 引用了不存在的图文文档 {t}')
    for m in manifest:
        for p in m.get('pages', []):
            if p not in keys:
                fail(f"MANIFEST {m.get('no')} 的页面 {p} 不在 ASSETS 里")
        for g in m.get('imgs', []):
            if g.get('k') not in keys:
                fail(f"MANIFEST {m.get('no')} 的图片 {g.get('k')} 不在 ASSETS 里")

    for k, v in assets.items():
        if k.startswith('pdf'):
            if v.startswith('data:'):
                fail(f"ASSETS['{k}'] 存了 data URI，pdf* 必须是**裸 base64**")
        elif not str(v).startswith('data:image/'):
            fail(f"ASSETS['{k}'] 不是 data URI，pg*/md* 必须是完整 data URI")

    srcs = {v.get('src') for p in data.get('panels', []) for it in p['items']
            for v in it['vals'] if v.get('src')}
    unknown = srcs - {r.get('no') for r in data.get('reports', [])}
    if unknown:
        fail(f"化验值的 src 指向不存在的报告：{'、'.join(sorted(unknown))}")


# --------------------------------------------------------------- 3. 交叉校验
def check_cross(data):
    """Recompute each flag from the range stored on that same measurement."""
    checked = mism = 0
    for p in data.get('panels', []):
        for it in p['items']:
            if not it.get('numeric'):
                continue                      # qualitative flags need the report's own words
            for v in it['vals']:
                if v.get('v') is None:
                    continue
                lo, hi = v.get('lo'), v.get('hi')
                if lo is None and hi is None:
                    continue                  # no printed range to check against
                checked += 1
                calc = 'H' if (hi is not None and v['v'] > hi) else \
                       ('L' if (lo is not None and v['v'] < lo) else None)
                if calc != v.get('f'):
                    mism += 1
                    fail(f"交叉校验不一致 · {p['label']} · {it['name']} · {v['d']}："
                         f"值 {v['t']}，参考区间 {v.get('ref')!r} 推出 {calc or '正常'}，"
                         f"但报告标的是 {v.get('f') or '正常'}")
    note(f'交叉校验：{checked} 次数值测量，{mism} 处不一致')
    if mism:
        note('  不一致 ≠ 数据错了，也**不是**让你改数——是报告印的箭头与它印的区间对不上。'
             '把这些列给用户核对原件，并把结论写进 data.footNotes。')
    qual = sum(1 for p in data.get('panels', []) for it in p['items']
               if not it.get('numeric') for v in it['vals'] if v.get('f'))
    if qual:
        note(f'另有 {qual} 个定性异常（隐血 +、清洁度 Ⅲ 之类）无法用区间自动校验，'
             '汇总表最容易漏标这类——请对着原件确认一遍（坑 §4.9）。')


# ----------------------------------------------------------------- 4. 零外链
# A base64 payload can never contain "://" (':' is outside the base64 alphabet), so a
# literal search for a scheme is safe against false hits from the embedded blobs.
NET_PATTERNS = [
    (r'(?:src|href)\s*=\s*["\']https?://', '指向外部 URL 的 src/href'),
    (r'\bfetch\s*\(', 'fetch()'),
    (r'\bXMLHttpRequest\b', 'XMLHttpRequest'),
    (r'\bnew\s+WebSocket\b', 'WebSocket'),
    (r'\bnew\s+EventSource\b', 'EventSource'),
    (r'navigator\.sendBeacon', 'sendBeacon'),
    (r'@import\s+url\(\s*["\']?https?://', '外链 CSS @import'),
    (r'\bimportScripts\s*\(', 'importScripts'),
]


def check_offline(html_path):
    with open(html_path, encoding='utf-8') as fh:
        html = fh.read()
    for pat, label in NET_PATTERNS:
        n = len(re.findall(pat, html))
        if n:
            fail(f'产物里有 {n} 处 {label} —— 页面必须零联网')
    stray = re.findall(r'https?://[^\s"\'<>)]{4,}', html)
    if stray:
        uniq = sorted(set(stray))[:5]
        note(f"产物里出现 {len(stray)} 处字面 URL（不触发请求，但会泄漏来源）：{'、'.join(uniq)}")
    note(f'产物 {os.path.basename(html_path)}：{os.path.getsize(html_path) / 1048576:.1f} MB')


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data', nargs='?', default='workspace/data.json')
    ap.add_argument('assets', nargs='?', default='workspace/assets.json')
    ap.add_argument('html', nargs='?', default=None)
    a = ap.parse_args()

    for p in (a.data, a.assets):
        if not os.path.exists(p):
            sys.exit(f'没有这个文件：{p}')
    with open(a.data, encoding='utf-8') as fh:
        data = json.load(fh)
    with open(a.assets, encoding='utf-8') as fh:
        bundle = json.load(fh)
    assets, manifest = bundle.get('assets', {}), bundle.get('manifest', [])

    check_contract(data)
    check_refs(data, assets, manifest)
    check_cross(data)
    if a.html:
        if os.path.exists(a.html):
            check_offline(a.html)
        else:
            fail(f'没有这个产物：{a.html}')
    else:
        note('没有传产物 HTML —— 零外链这一项没查。')

    n_items = sum(len(p['items']) for p in data.get('panels', []))
    print(f"{len(data.get('reports', []))} 份报告 · {len(data.get('panels', []))} 个面板 / "
          f"{n_items} 项化验 · {len(assets)} 个资产 · {len(manifest)} 个文档")
    for n in notes:
        print(OK, n)
    if issues:
        print(f'\n发现 {len(issues)} 个问题：')
        for i in issues:
            print(BAD, i)
        print('\n注意：交叉校验不一致时**不要改数**，列给用户核对原件。')
        return 1
    print('\n契约、引用、交叉校验、零外链 —— 四项全过。')
    print('还没完：打开浏览器，按 docs/30-build-verify.md 的清单点一遍。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
