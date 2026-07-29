#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synthesize the demo's medical-looking illustrations — all of them fabricated.

    python3 demo/gen_images.py                 # nothing to do; demo/assets/ is committed
    python3 demo/gen_images.py --regen         # regenerate: AI if a key is present, else PIL
    python3 demo/gen_images.py --regen --engine pil    # force the dependency-free path
    python3 demo/gen_images.py --regen --engine ai     # force gpt-image-2.0, fail loudly

Two engines, one guarantee. `pil` draws stylized ultrasound
figures from numpy noise — no API key, no network, byte-reproducible from the seed, so
anyone who clones the repo can rebuild every asset. `ai` asks gpt-image-2.0 for a nicer
looking illustration and falls back to `pil` per-image if the call fails.

WHICHEVER engine runs, every image leaves through save_webp(), and save_webp() stamps
the "DEMO · 合成示例 · 非真实医疗影像" watermark before writing. That is deliberate: the
watermark is not the generator's job to remember, it is structurally unavoidable. These
figures must never be mistakable for a real person's medical imaging.
"""
import argparse, base64, io, os, sys

import fitz
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'assets')
RAW_CACHE = os.path.join(HERE, '.raw_cache')      # unstamped originals, gitignored
WATERMARK = 'DEMO · 合成示例 · 非真实医疗影像'


# ----------------------------------------------------------------- watermark
def _cjk_layer(w, h, items):
    """Render CJK text to an RGBA overlay. PyMuPDF carries a built-in Simplified
    Chinese face ('china-s'), so this needs no system font and works everywhere."""
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    for x, y, size, text, color, alpha in items:
        page.insert_text((x, y), text, fontsize=size, fontname='china-s',
                         color=color, fill_opacity=alpha)
    pix = page.get_pixmap(alpha=True)
    layer = Image.frombytes('RGBA', (pix.width, pix.height), pix.samples)
    doc.close()
    return layer


def stamp(im):
    """Overlay the synthetic-data watermark. Applied to every image, no exceptions."""
    im = im.convert('RGB')
    w, h = im.size
    size = max(13, int(w / 22))
    step = max(int(h / 3.2), size * 3)

    # Ink colour follows the image: white washes out on bright frames, black
    # disappears on a dark ultrasound. Pick per image so the notice always reads.
    ink = (0, 0, 0) if np.asarray(im.convert('L'), dtype=np.float32).mean() > 118 else (1, 1, 1)
    tiled = [(-size * 0.7 + (i % 2) * size * 1.6, y, size, WATERMARK, ink, 0.46)
             for i, y in enumerate(range(step, h, step))]
    layer = _cjk_layer(w, h, tiled)
    im.paste(layer, (0, 0), layer)

    # A solid footer bar, so the notice survives cropping the middle of the image.
    bar_h = max(20, int(h * 0.075))
    bar = Image.new('RGBA', (w, bar_h), (0, 0, 0, 205))
    im.paste(bar, (0, h - bar_h), bar)
    fs = max(10, int(bar_h * 0.56))
    foot = _cjk_layer(w, h, [(8, h - bar_h + (bar_h + fs) / 2 - 2, fs,
                              WATERMARK, (1, 0.87, 0.35), 1.0)])
    im.paste(foot, (0, 0), foot)
    return im


def save_webp(im, key, quality=80):
    """The only way an image reaches disk — hence the only place the stamp is needed."""
    path = os.path.join(OUT, key + '.webp')
    stamp(im).save(path, 'WEBP', quality=quality, method=6)
    return path


# ------------------------------------------------------------- PIL generators
def _speckle(rng, h, w, coarse=8):
    """Ultrasound-looking granular texture: blocky low-frequency blobs + fine grain."""
    lo = rng.random((max(2, h // coarse), max(2, w // coarse)))
    lo = np.array(Image.fromarray((lo * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)) / 255
    return np.clip(0.62 * lo + 0.38 * rng.random((h, w)), 0, 1)


def pil_ultrasound(seed, nodule=True, nodule_pos=(0.42, 0.46), nodule_size=(0.10, 0.07)):
    """A grayscale sector scan: speckle field, tissue banding, an optional hypoechoic
    lesion with a bright rim, plus calipers and a depth ruler. Stylized on purpose."""
    W, H = 640, 480
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    nx, ny = (xx - W / 2) / (W / 2), yy / H

    field = _speckle(rng, H, W) * 0.55
    field += 0.22 * np.exp(-((ny - 0.16) ** 2) / 0.006)     # near-field bright band
    field += 0.14 * np.exp(-((ny - 0.62) ** 2) / 0.05)      # deeper tissue plane
    field *= np.clip(1.15 - ny * 0.75, 0.25, 1.15)          # depth attenuation

    if nodule:
        cx, cy = nodule_pos
        rx, ry = nodule_size
        d = np.sqrt(((nx - (cx * 2 - 1)) / rx) ** 2 + ((ny - cy) / ry) ** 2)
        field = np.where(d < 1.0, field * 0.22, field)                  # hypoechoic core
        field += np.where((d >= 0.96) & (d < 1.22), 0.30, 0.0)          # echogenic rim

    # Sector geometry: apex just below the top edge, ~66° total aperture.
    ang = np.abs(np.arctan2(nx * (W / 2), (yy - 8) + 1e-6))
    rad = np.sqrt((nx * (W / 2)) ** 2 + (yy - 8) ** 2)
    field = np.where((ang < 0.58) & (rad < H * 0.99) & (yy > 12), field, 0.0)

    im = Image.fromarray((np.clip(field, 0, 1) * 255).astype(np.uint8)).convert('RGB')
    d = ImageDraw.Draw(im)
    for i in range(1, 9):                                   # depth ruler
        y = int(H * i / 9)
        d.line([(W - 14, y), (W - 6, y)], fill=(180, 180, 180), width=1)
    if nodule:                                              # measurement calipers
        cx, cy = int(nodule_pos[0] * W), int(nodule_pos[1] * H)
        rx, ry = int(nodule_size[0] * W / 2), int(nodule_size[1] * H)
        for px, py in ((cx - rx, cy), (cx + rx, cy), (cx, cy - ry), (cx, cy + ry)):
            d.line([(px - 6, py), (px + 6, py)], fill=(255, 240, 90), width=1)
            d.line([(px, py - 6), (px, py + 6)], fill=(255, 240, 90), width=1)
        d.line([(cx - rx, cy), (cx + rx, cy)], fill=(255, 240, 90), width=1)
    return im


# ---------------------------------------------------------------- AI generator
# Tried in order — accounts differ in which image models they can reach.
AI_MODELS = ('gpt-image-2', 'gpt-image-1')
AI_STYLE = ('A stylized, clearly diagrammatic illustration in the visual style of {}. '
            'This is synthetic artwork for a software demo — not a real medical scan, '
            'no patient information, no hospital branding, no readable text, no letters '
            'or digits, and no logos anywhere in the image.')


def ai_generate(subject, size='1024x1024'):
    """Ask an OpenAI image model for an illustration. Returns a PIL image, or None so
    the caller falls back to PIL — the API is never a hard dependency."""
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
    except Exception as e:
        print(f'    openai sdk unavailable ({e}) → PIL', file=sys.stderr)
        return None
    for model in AI_MODELS:
        try:
            r = client.images.generate(model=model, prompt=AI_STYLE.format(subject),
                                       size=size, n=1)
            return Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json)))
        except Exception as e:                   # model missing, quota, network…
            print(f'    {model}: {type(e).__name__}: {str(e)[:120]}', file=sys.stderr)
    print('    all image models failed → falling back to PIL', file=sys.stderr)
    return None


# ------------------------------------------------------------------- manifest
# key → (kind, seed, ai-subject, pil-kwargs).  The lesions grow across the three visits
# so the pictures track the TI-RADS 3 → 3 → 4a and the carotid-plaque storyline that
# make_demo.py writes into the report text. Both engines follow the same progression.
_THY = 'a grayscale thyroid ultrasound sector scan showing the thyroid lobes beside the trachea'
_CAR = ('a grayscale carotid artery ultrasound long-axis scan showing a horizontal '
        'vessel lumen between two bright intima-media lines')
_ABD = 'a grayscale abdominal ultrasound sector scan showing a uniform liver parenchyma'

SPEC = [
    ('us_thy_2024_a', 'us', 101, _THY + ', with one small dark round nodule in the left lobe', dict(nodule_size=(0.075, 0.052))),
    ('us_thy_2024_b', 'us', 102, _THY + ', right lobe, uniform tissue with no lesion', dict(nodule=False)),
    ('us_car_2024_a', 'us', 111, _CAR + ', clean vessel wall with no plaque', dict(nodule=False)),
    ('us_car_2024_b', 'us', 112, _CAR + ', internal carotid, uniform flow lumen', dict(nodule=False)),
    ('us_thy_2025_a', 'us', 201, _THY + ', with one small dark round nodule in the left lobe', dict(nodule_size=(0.085, 0.058))),
    ('us_thy_2025_b', 'us', 202, _THY + ', right lobe, uniform tissue with no lesion', dict(nodule=False)),
    ('us_car_2025_a', 'us', 211, _CAR + ', with one small flat bright plaque on the far wall', dict(nodule_size=(0.09, 0.03), nodule_pos=(0.55, 0.56))),
    ('us_abd_2025_a', 'us', 221, _ABD, dict(nodule=False)),
    ('us_thy_2026_a', 'us', 301, _THY + ', with one larger dark irregular nodule in the left lobe', dict(nodule_size=(0.115, 0.082))),
    ('us_thy_2026_b', 'us', 302, _THY + ', right lobe, with one tiny dark spot', dict(nodule_size=(0.05, 0.04), nodule_pos=(0.62, 0.55))),
    ('us_car_2026_a', 'us', 311, _CAR + ', with one flat bright plaque, slightly larger', dict(nodule_size=(0.12, 0.035), nodule_pos=(0.55, 0.56))),
]
# Ultrasound only, and that is the realistic picture. In the real exports this project
# was built from, every extractable diagnostic image came from ultrasound; the CT / DR /
# ECG report PDFs embedded nothing but a logo and a QR code (an ECG's waveform is vector
# art, so there is no bitmap to pull). Those demo reports therefore carry no image either,
# and DATA.galleryNote explains the absence instead of papering over it (坑 §4.4).
# (Sex-specific subjects such as mammography are absent by design; the models refuse them
# anyway. Endoscopy was dropped deliberately — too visceral for a public demo page.)
_PIL = {'us': pil_ultrasound}
_AI_SIZE = {'us': '1024x1024'}
_BOX = {'us': (640, 480)}


def build_one(entry, use_ai, cache=True):
    """Produce one asset. Returns (key, engine-actually-used).

    Generated originals are cached unstamped under demo/.raw_cache/ (gitignored), so
    tweaking the watermark or the output size is a local re-render rather than another
    round of paid API calls. Delete the directory, or pass --no-cache, to refetch."""
    key, kind, seed, subject, kw = entry
    raw = os.path.join(RAW_CACHE, key + '.png')
    im = None
    if use_ai and cache and os.path.exists(raw):
        im = Image.open(raw)
    elif use_ai:
        im = ai_generate(subject, _AI_SIZE[kind])
        if im is not None and cache:
            os.makedirs(RAW_CACHE, exist_ok=True)
            im.convert('RGB').save(raw)
    engine = 'ai' if im is not None else 'pil'
    im = im.convert('RGB').resize(_BOX[kind], Image.LANCZOS) if im is not None \
        else _PIL[kind](seed, **kw)
    save_webp(im, key)
    return key, engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--regen', action='store_true', help='rebuild demo/assets/*.webp')
    ap.add_argument('--engine', choices=('auto', 'ai', 'pil'), default='auto')
    ap.add_argument('--jobs', type=int, default=6, help='parallel image requests (ai only)')
    ap.add_argument('--no-cache', action='store_true',
                    help='ignore demo/.raw_cache and refetch every image from the API')
    a = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    if not a.regen:
        have = len([f for f in os.listdir(OUT) if f.endswith('.webp')])
        print(f'{have}/{len(SPEC)} images already in demo/assets/ — pass --regen to rebuild')
        return 0 if have >= len(SPEC) else 1

    use_ai = a.engine == 'ai' or (a.engine == 'auto' and os.environ.get('OPENAI_API_KEY'))
    if a.engine == 'ai' and not os.environ.get('OPENAI_API_KEY'):
        sys.exit('--engine ai needs OPENAI_API_KEY in the environment')
    print(f'engine: {"/".join(AI_MODELS) + " (per-image PIL fallback)" if use_ai else "PIL"}')

    if use_ai:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
            done = list(pool.map(lambda e: build_one(e, True, not a.no_cache), SPEC))
    else:
        done = [build_one(e, False) for e in SPEC]

    n_ai = sum(1 for _, eng in done if eng == 'ai')
    print(f'{len(done)} images → demo/assets/  ({n_ai} generated, '
          f'{len(done) - n_ai} drawn with PIL) · all watermarked')
    return 0


if __name__ == '__main__':
    sys.exit(main())
