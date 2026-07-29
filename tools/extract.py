#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Get the contents of a document out, by whichever of the two layers applies.

    python3 tools/extract.py text   report.pdf              # layer 1: the text layer
    python3 tools/extract.py pages  scan.pdf                # layer 2: render → you read
    python3 tools/extract.py images report.pdf              # embedded diagnostic images
    python3 tools/extract.py text   report.pdf --json       # {page: text} for scripting

There is no OCR engine here and that is the point. Layer 1 (a PDF with a text layer)
gives exact characters at zero cost. Layer 2 (a scan, a phone photo, a long screenshot,
a video frame) renders to PNG — and then *you*, the agent running this repo, open the
PNG with Read and read it. You are a multimodal model; you outread any OCR engine on a
Chinese lab sheet, and this keeps the project dependency-free and cross-platform.

Layer 3, for when there is too much to hold at once, is tools/fanout.py.
"""
import argparse, json, os, shutil, sys

OUT_DEFAULT = os.path.join('workspace', 'raw')
IMG_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp'}
DECOR_MAX_PX = 160        # below this an embedded image is a logo / QR / signature


def _outdir(path, sub, explicit=None):
    d = explicit or os.path.join(OUT_DEFAULT, sub,
                                 os.path.splitext(os.path.basename(path))[0])
    os.makedirs(d, exist_ok=True)
    return d


def cmd_text(a):
    import fitz
    doc = fitz.open(a.file)
    if doc.needs_pass:
        sys.exit(f'{a.file} 有密码保护。请用户自己解开后再放进来——不要去猜密码。')
    pages = {i + 1: p.get_text() for i, p in enumerate(doc)}
    total = sum(len(t.strip()) for t in pages.values())
    doc.close()
    if a.json:
        print(json.dumps(pages, ensure_ascii=False, indent=1))
        return 0
    if total < 40 * len(pages):
        print(f'⚠ 文字层几乎是空的（{total} 字 / {len(pages)} 页）——这是扫描件或照片版。\n'
              f'  改用：python3 tools/extract.py pages {a.file}   然后用 Read 打开图片自己读\n',
              file=sys.stderr)
    for n, t in pages.items():
        print(f'\n===== 第 {n}/{len(pages)} 页 =====')
        print(t.rstrip())
    return 0


def cmd_pages(a):
    """Render each page to PNG. These are for the agent to look at, not to embed —
    embedding into the dashboard is build_assets.py's job (WebP, much smaller)."""
    out = _outdir(a.file, 'pages', a.out)
    ext = os.path.splitext(a.file)[1].lower()
    if ext in IMG_EXT:                      # already an image; normalise and hand it over
        dst = os.path.join(out, 'page_001' + ext)
        shutil.copyfile(a.file, dst)
        print(dst)
        print(f'\n1 张图 → {out}/\n用 Read 打开它，把上面的数值读出来。', file=sys.stderr)
        return 0

    import fitz
    doc = fitz.open(a.file)
    if doc.needs_pass:
        sys.exit(f'{a.file} 有密码保护。请用户自己解开后再放进来。')
    written = []
    for i, page in enumerate(doc):
        dst = os.path.join(out, f'page_{i + 1:03d}.png')
        page.get_pixmap(dpi=a.dpi).save(dst)
        written.append(dst)
        print(dst)
    doc.close()
    print(f'\n{len(written)} 页 @ {a.dpi}dpi → {out}/\n'
          f'用 Read 逐张打开读数。异常值请复读一次再定稿；读不清就标「待核对」，不要猜。',
          file=sys.stderr)
    return 0


def cmd_images(a):
    """Pull embedded raster images. Imaging PDFs are mostly text — what is embedded is
    usually a logo, a QR code or a signature, so anything small is dropped (坑 §4.4)."""
    import fitz
    doc = fitz.open(a.file)
    out = _outdir(a.file, 'images', a.out)
    kept, skipped = 0, 0
    seen = set()
    for pno, page in enumerate(doc):
        for img in page.get_images(full=True):
            try:
                d = doc.extract_image(img[0])
            except Exception:
                continue
            if max(d['width'], d['height']) <= a.min_px:
                skipped += 1
                continue
            import hashlib
            sig = hashlib.md5(d['image']).hexdigest()      # same frame on several pages
            if sig in seen:
                skipped += 1
                continue
            seen.add(sig)
            dst = os.path.join(out, f"p{pno + 1:02d}_{kept:02d}.{d['ext']}")
            with open(dst, 'wb') as fh:
                fh.write(d['image'])
            print(f"{dst}  {d['width']}×{d['height']}")
            kept += 1
    doc.close()
    print(f'\n{kept} 张留下 → {out}/  ({skipped} 张被当作装饰件或重复帧跳过，'
          f'阈值 {a.min_px}px)\n'
          f'如果一张都没留下，多半这份报告 PDF 本来就没有诊断图——很常见，'
          f'去 galleryNote 里如实说明即可。', file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('text', help='第1层：直接取 PDF 文字层')
    p.add_argument('file'); p.add_argument('--json', action='store_true')
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser('pages', help='第2层：整页渲染成 PNG，交给 agent 自己读')
    p.add_argument('file'); p.add_argument('--dpi', type=int, default=170)
    p.add_argument('--out', default=None)
    p.set_defaults(fn=cmd_pages)

    p = sub.add_parser('images', help='抽出内嵌的诊断图（自动跳过院徽/二维码/重复帧）')
    p.add_argument('file'); p.add_argument('--min-px', type=int, default=DECOR_MAX_PX)
    p.add_argument('--out', default=None)
    p.set_defaults(fn=cmd_images)

    a = ap.parse_args()
    if not os.path.exists(a.file):
        sys.exit(f'没有这个文件：{a.file}')
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
