#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""起点脚本：把 workspace/inbox/ 里的报告原件变成 assets.json。**复制到 workspace/ 再改。**

    cp starter/build_assets.py workspace/
    cd workspace && python3 build_assets.py

它按最常见的形态先跑通一遍：一份 PDF = 一份报告，按内容 hash 去重，整页渲染成 WebP，
再从中挑出够大的内嵌图当诊断图。**这只是起点**——每个人的数据都不一样，
照着 docs/20-extract.md 的 9 个坑对照改。标了 TODO 的地方是最常需要动的。

产出 assets.json = {assets: {键: 值}, manifest: [每个文档一条]}，字段定义见
docs/DATA_CONTRACT.md。报告的文字内容不在这里处理，那是 build_data.py 的事。
"""
import base64, io, json, os, re, sys

import fitz
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from lib import dedup_pdfs, img_sig, trim, webp_b64                 # noqa: E402

INBOX = 'inbox'                 # 相对 workspace/；解压出来的放 raw/ 就改成 'raw'
PAGE_WIDTH = 1300               # 整页渲染的目标宽度；报告页 1300 够看清
PAGE_DPI = 150
DECOR_MAX_PX = 160              # 比这小的内嵌图是院徽/二维码/签名，不是诊断图（坑 §4.4）
EMBED_PDF = True                # TODO 设 False 可瘦身：不内嵌 PDF 原件，只留页面渲染图

ASSETS, MANIFEST = {}, []


def report_no(path):
    """从文件名里取报告编号。TODO 按你的文件名规律改——最好别信文件名里的日期（坑 §4.6），
    日期以 PDF 正文里印的为准，那个在 build_data.py 里处理。"""
    m = re.match(r'(\d{1,3})[_\-. ]', os.path.basename(path))
    return m.group(1).zfill(2) if m else None


def page_images(doc, no):
    keys = []
    for i, page in enumerate(doc):
        im = Image.open(io.BytesIO(page.get_pixmap(dpi=PAGE_DPI).tobytes('png')))
        key = f'pg{no}_{i}'
        ASSETS[key] = webp_b64(im, width=PAGE_WIDTH, quality=80)
        keys.append(key)
    return keys


def diagnostic_images(doc, no):
    """挑出真正的诊断图。小的是装饰件，重复的是同一帧出现在多页上。
    TODO 内镜常把 8 张图拼在一整页扫描图里（坑 §4.5）——那种要按固定行列坐标裁，
    用 PIL 的 im.crop((l, t, r, b))，别指望 get_images() 能拆开。"""
    out, seen = [], set()
    for page in doc:
        for img in page.get_images(full=True):
            try:
                d = doc.extract_image(img[0])
            except Exception:
                continue
            if max(d['width'], d['height']) <= DECOR_MAX_PX:
                continue
            sig = img_sig(d['image'])
            if sig in seen:
                continue
            seen.add(sig)
            im = Image.open(io.BytesIO(d['image']))
            key = f'md{no}_{len(out)}'
            ASSETS[key] = webp_b64(trim(im), quality=84)
            # TODO 图注：写清楚这是哪个部位第几张。读不出部位就按序号写「超声图 1/4」，
            # **别猜部位**——写错部位比不写更糟。
            out.append({'k': key, 'cap': f'图 {len(out) + 1}'})
    return out


def main():
    if not os.path.isdir(INBOX):
        sys.exit(f'没有 {INBOX}/ 目录。先把报告放进 workspace/inbox/，'
                 f'再跑 python3 ../tools/probe.py inbox 看看是什么形态。')
    pdfs = [os.path.join(dp, f) for dp, _, fs in os.walk(INBOX)
            for f in sorted(fs) if f.lower().endswith('.pdf')]
    if not pdfs:
        sys.exit(f'{INBOX}/ 里没有 PDF。只有图片的话走 docs/12-acquire-manual.md 的照片路线。')

    # 坑 §4.6：导出包常把同一份文档按每个检查名各存一份。先按内容 hash 归并，
    # 每组只留一份，被合并掉的文件名记进 aliases，用户还能按自己知道的名字找到它。
    groups = dedup_pdfs(pdfs)
    print(f'{len(pdfs)} 个 PDF → {len(groups)} 份不同文档')

    for i, (_, paths) in enumerate(sorted(groups.items(), key=lambda kv: kv[1][0]), 1):
        primary = paths[0]
        no = report_no(primary) or f'{i:02d}'
        doc = fitz.open(primary)
        if doc.needs_pass:
            print(f'  ⚠ {primary} 有密码，跳过。请用户自己解开再放进来。')
            doc.close()
            continue
        if EMBED_PDF:
            with open(primary, 'rb') as fh:
                ASSETS['pdf' + no] = base64.b64encode(fh.read()).decode()
        entry = {'kind': 'report', 'no': no, 'file': os.path.basename(primary),
                 'pages': page_images(doc, no), 'imgs': diagnostic_images(doc, no)}
        if len(paths) > 1:
            entry['aliases'] = [os.path.basename(p) for p in paths[1:]]
        # TODO 如果这份是「图文报告」（一份文档覆盖同一次的多项检查），把 kind 改成 'tw'，
        # 再在 build_data.py 里用 report.tw = ['<这个 no>'] 挂上去。见契约里的两种挂图方式。
        MANIFEST.append(entry)
        doc.close()
        print(f"  {no}  {os.path.basename(primary)}  "
              f"{len(entry['pages'])}页 · {len(entry['imgs'])}图"
              + (f" · 另有 {len(paths) - 1} 个同内容副本" if len(paths) > 1 else ''))

    with open('assets.json', 'w', encoding='utf-8') as fh:
        json.dump({'assets': ASSETS, 'manifest': MANIFEST}, fh, ensure_ascii=False)
    mb = os.path.getsize('assets.json') / 1048576
    print(f'\nassets.json  {mb:.1f} MB · {len(ASSETS)} 个资产 · {len(MANIFEST)} 个文档')
    if not any(m['imgs'] for m in MANIFEST):
        print('注意：一张诊断图都没提取到。影像报告 PDF 常常本来就只有文字（坑 §4.4），'
              '这很正常——在 data.json 的 galleryNote 里如实说明就好。')


if __name__ == '__main__':
    main()
