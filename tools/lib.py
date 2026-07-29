#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Format-agnostic helpers shared by the build scripts. Import what you need:

    import sys; sys.path.insert(0, 'tools')      # or wherever this repo lives
    from lib import unzip_cjk, trim, webp_b64, dedup_pdfs, parse_ref, parse_val, \
                    qual_flag, cluster_dates, pdf_b64

None of this is specific to a hospital or export format — the data-shape logic lives
in the per-dataset build_data.py / build_assets.py you copy out of starter/ into
workspace/. See docs/20-extract.md for which helper defuses which known data trap.
"""
import base64, hashlib, io, os, re, unicodedata, zipfile


# ----------------------------------------------------------------- extraction
def unzip_cjk(zip_path, out_dir):
    """Extract a zip, fixing the mojibake that Windows-made archives cause on macOS
    (CJK names stored as cp437). Returns the list of extracted relative paths."""
    os.makedirs(out_dir, exist_ok=True)
    names = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):     # not UTF-8 flagged → guess
                raw = name.encode('cp437', 'ignore')
                for enc in ('utf-8', 'gbk', 'big5'):
                    try:
                        name = raw.decode(enc); break
                    except Exception:
                        continue
            target = os.path.join(out_dir, name)
            if info.is_dir():
                os.makedirs(target, exist_ok=True); continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, 'wb') as dst:
                dst.write(src.read())
            names.append(name)
    return names


# --------------------------------------------------------------------- images
def trim(im, thresh=246, pad_frac=0.012):
    """Crop surrounding whitespace off a rendered page. `im` is a PIL image."""
    import numpy as np
    a = np.asarray(im.convert('L'))
    m = a < thresh
    if not m.any():
        return im
    r, c = np.where(m.any(1))[0], np.where(m.any(0))[0]
    py, px = max(6, int(im.height * pad_frac)), max(6, int(im.width * pad_frac))
    return im.crop((max(0, c[0] - px), max(0, r[0] - py),
                    min(im.width, c[-1] + px), min(im.height, r[-1] + py)))


def webp_b64(im, width=None, quality=82):
    """PIL image → WebP data URI. WebP ~halves JPEG on text-heavy scans at equal
    legibility. Downscale wide scans to ~1300px; medical frames keep native size."""
    im = im.convert('RGB')
    if width and im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))))
    b = io.BytesIO()
    im.save(b, 'WEBP', quality=quality, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(b.getvalue()).decode()


def pdf_b64(path):
    """Raw base64 of a PDF (no data: prefix) — the form ASSETS['pdf<no>'] expects."""
    return base64.b64encode(open(path, 'rb').read()).decode()


# ---------------------------------------------------------------------- dedup
def dedup_pdfs(paths):
    """Group identical files by content hash. Exports often save one document under
    several names (one per exam of a session); returns {hash: [paths...]}."""
    groups = {}
    for p in sorted(paths):
        h = hashlib.md5(open(p, 'rb').read()).hexdigest()[:10]
        groups.setdefault(h, []).append(p)
    return groups


def img_sig(image_bytes):
    """Content hash of image bytes — dedup frames repeated across a doc's pages."""
    return hashlib.md5(image_bytes).hexdigest()


# --------------------------------------------------------------- lab parsing
_RANGE = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*[-~－]\s*(-?\d+(?:\.\d+)?)\s*$')
_GE = re.compile(r'^\s*[≥>]=?\s*(-?\d+(?:\.\d+)?)')
_LE = re.compile(r'^\s*[≤<]=?\s*(-?\d+(?:\.\d+)?)')


def parse_ref(s):
    """Reference range text → (lo, hi); either side None for an open criterion
    ('≥50 正常' → (50, None)). Returns (None, None) for qualitative refs ('阴性')."""
    if not s:
        return None, None
    s = str(s).strip()
    m = _RANGE.match(s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _GE.match(s)
    if m:
        return float(m.group(1)), None
    m = _LE.match(s)
    if m:
        return None, float(m.group(1))
    return None, None


def parse_val(raw):
    """Result cell → (number|None, flag, display text). Reads the lab's own ↑/↓
    arrows; leaves numeric range-checking to the caller (ranges are per-date)."""
    if raw is None or str(raw).strip() == '':
        return None, None, None
    s = str(raw).strip()
    flag = 'H' if '↑' in s else ('L' if '↓' in s else None)
    s2 = s.replace('↑', '').replace('↓', '').strip()
    num = float(s2) if re.fullmatch(r'-?\d+(?:\.\d+)?', s2) else None
    return num, flag, s2


_ROMAN = {'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'I': 1, 'II': 2, 'III': 3, 'IV': 4}


def qual_flag(text, ref):
    """Flag a qualitative result the numeric path can't see (隐血 +++, 清洁度 Ⅲ).
    Returns 'A' (abnormal) or None. Extend the rules per your reference vocabulary."""
    v, r = (text or '').strip(), (ref or '').strip()
    if not v:
        return None
    if '阴性' in r or r == '-':
        return 'A' if v.startswith('+') else None
    if r in ('I-II', 'I~II'):
        n = _ROMAN.get(v)
        return 'A' if n and n > 2 else None
    if r == '正常':
        return None if v == '正常' else 'A'
    return None


def norm(s):
    """Normalize a name for matching across sheets/OCR (full/half width, spaces)."""
    s = unicodedata.normalize('NFKC', str(s or '')).strip()
    return re.sub(r'\s+', '', s.replace('（', '(').replace('）', ')'))


# --------------------------------------------------------------- visit clusters
def cluster_dates(dates, gap_days=21):
    """Group dates into visit batches (one check-up spread over several days).
    Returns [{id, label, dates[], span}] for DATA.clusters."""
    from datetime import date as D
    ds = sorted(set(dates))
    out, cur = [], []
    for d in ds:
        y, m, dd = map(int, d.split('-'))
        if cur:
            py, pm, pdd = map(int, cur[-1].split('-'))
            if (D(y, m, dd) - D(py, pm, pdd)).days > gap_days:
                out.append(cur); cur = []
        cur.append(d)
    if cur:
        out.append(cur)
    return [{'id': c[0], 'label': c[0][:7].replace('-', '年') + '月',
             'dates': c, 'span': c[0] if len(c) == 1 else f'{c[0]} ~ {c[-1]}'} for c in out]
