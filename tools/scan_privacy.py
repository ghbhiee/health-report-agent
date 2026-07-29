#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan the repository for anything that must never be published.

    python3 tools/scan_privacy.py                    # scan the repo
    python3 tools/scan_privacy.py --name 张三 李四    # also hunt for specific names

Run this before every commit and again before pushing. It looks for:

  · 身份证号 / 手机号 / 邮箱 / 银行卡号
  · 病历号、门诊号、住院号、就诊卡号 后面跟着的数字
  · 用 --name 传进来的真实姓名（姓名没法靠正则认，只能你告诉它）
  · 该被 .gitignore 挡住却出现在仓库里的产物 HTML 和用户数据

`workspace/` is skipped by design — that is where the user's own records live and it is
gitignored. Everything else in the tree is a candidate for publication and is scanned.

Exit code 0 clean, 1 something to look at. This is a net, not a guarantee: a real name
written in prose looks exactly like any other text, so pass --name for anyone whose data
you have touched, and read the diff yourself before pushing.
"""
import argparse, os, re, subprocess, sys

SKIP_DIRS = {'.git', 'workspace', '__pycache__', '.venv', 'venv', 'node_modules',
             '.raw_cache', 'videos'}
SKIP_EXT = {'.webp', '.png', '.jpg', '.jpeg', '.pdf', '.zip', '.woff', '.woff2',
            '.ttf', '.ico', '.mp4', '.mov'}
MAX_BYTES = 64_000_000         # a built dashboard is one huge line; read all of it

# Every quantifier here is bounded on purpose. A built dashboard is a single line of
# several million characters, and an unbounded `[\w.+-]+@` degrades to O(n²) on it —
# the scan then hangs instead of reporting, which is the worst possible failure mode
# for a check that runs right before you publish.
PATTERNS = [
    ('身份证号', re.compile(r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}'
                            r'(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)')),
    ('手机号', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ('邮箱', re.compile(r'[\w.+-]{1,64}@[\w-]{1,63}\.[\w.]{2,24}')),
    ('银行卡号', re.compile(r'(?<!\d)\d{16,19}(?!\d)')),
    ('病历/门诊/住院号', re.compile(r'(病案号|病历号|门诊号|住院号|就诊卡号|登记号|检查号)'
                                    r'[：:\s]{0,4}([A-Za-z0-9-]{4,32})')),
]

# Things that legitimately match but are not private data.
ALLOW = re.compile(
    r'noreply@|example\.com|example\.invalid|@myhexin\.com|'
    r'报告编号\s*SY|'                                # the demo's fabricated report ids
    r'ghbhiee|users\.noreply\.github\.com|'
    r'guohongbo@outlook\.com|'    # the project's declared public author contact
    r'[\w.-]+@\d+\.\d+'         # npm/CDN version specs, e.g. gsap@3.14.2
)


def files(root):
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.git')]
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in SKIP_EXT:
                continue
            p = os.path.join(dirpath, n)
            if os.path.islink(p):
                continue
            yield p


def scan_text(root, extra_names):
    hits = []
    name_re = re.compile('|'.join(re.escape(n) for n in extra_names)) if extra_names else None
    for p in files(root):
        try:
            with open(p, encoding='utf-8', errors='ignore') as fh:
                text = fh.read(MAX_BYTES)
        except Exception:
            continue
        rel = os.path.relpath(p, root)
        # Scan whole lines, however long. A built dashboard inlines data.json onto one
        # multi-megabyte line — truncating it would walk straight past the one place a
        # real name is most likely to be hiding. Every pattern here is linear, so this
        # is cheap even on a 30MB blob.
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in PATTERNS:
                for m in pat.finditer(line):
                    if ALLOW.search(m.group(0)):
                        continue
                    hits.append((rel, lineno, label, m.group(0)[:60]))
            if name_re:
                for m in name_re.finditer(line):
                    hits.append((rel, lineno, '真实姓名', m.group(0)))
    return hits


def scan_tracked(root):
    """Anything git would actually publish that should have been ignored."""
    problems = []
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=root, capture_output=True,
                             text=True, timeout=30)
        if out.returncode != 0:
            return [('（还不是 git 仓库，跳过 git 检查）', None)]
        tracked = out.stdout.split()
    except Exception as e:
        return [(f'（git 检查跳过：{e}）', None)]

    for f in tracked:
        if f.startswith('workspace/') and not f.endswith('.gitkeep'):
            problems.append((f, '用户数据目录里的文件被 git 跟踪了'))
        # index.html 是 GitHub Pages 的根跳转页，几行静态 HTML、不含任何数据
        if f.endswith('.html') and f not in ('demo/index.html', 'template/app_template.html',
                                             'index.html'):
            problems.append((f, '产物 HTML 被 git 跟踪了'))
        if f.endswith(('data.json', 'assets.json')):
            problems.append((f, '中间数据被 git 跟踪了'))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', nargs='?', default='.')
    ap.add_argument('--name', nargs='*', default=[],
                    help='要额外搜的真实姓名（姓名认不出来，只能你告诉它）')
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    hits = scan_text(root, a.name)
    tracked = scan_tracked(root)

    n_files = sum(1 for _ in files(root))
    print(f'扫了 {n_files} 个文本文件（跳过 workspace/ 与二进制）')
    if a.name:
        print(f"额外搜的姓名：{'、'.join(a.name)}")
    else:
        print('提示：没传 --name。姓名没法靠正则认出来——把你经手过的真实姓名传进来再扫一遍。')

    bad = False
    if hits:
        bad = True
        print(f'\n可能的隐私数据 {len(hits)} 处：')
        for rel, ln, label, s in hits[:80]:
            print(f'  ✗ {rel}:{ln}  [{label}]  {s}')
        if len(hits) > 80:
            print(f'  … 还有 {len(hits) - 80} 处')
    if tracked:
        real = [t for t in tracked if t[1]]
        for f, why in tracked:
            if why is None:
                print(f'\n{f}')
        if real:
            bad = True
            print(f'\n不该进 git 的文件 {len(real)} 个：')
            for f, why in real:
                print(f'  ✗ {f}  —— {why}')

    if not bad:
        print('\n没有发现问题。但这只是一张网，不是保证——push 前请自己再看一遍 diff。')
        return 0
    print('\n发布前必须清理干净。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
