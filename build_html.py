#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Splice data.json + assets.json into the template → one self-contained .html.

    python3 build_html.py [OUTPUT.html] [--template PATH] [--data PATH] [--assets PATH]

Defaults: reads ./data.json and ./assets.json, uses ../template/app_template.html
(or ./app_template.html if present), writes ./健康档案.html. The template has three
placeholders — /*__DATA__*/null, /*__ASSETS__*/null, /*__MANIFEST__*/null — replaced
with the JSON literals. Nothing else is transformed, so the output is byte-for-byte
the template plus embedded data: no network, no build step, double-click to open.
"""
import argparse, json, os, sys


def js(obj):
    """JSON safe to inline inside a <script> block (escape </script and U+2028/9)."""
    return (json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
            .replace('</script', '<\\/script')
            .replace(' ', '\\u2028').replace(' ', '\\u2029'))


def find_template():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in ('app_template.html',
              os.path.join(here, 'template', 'app_template.html'),
              os.path.join(here, 'app_template.html')):
        if os.path.exists(p):
            return p
    sys.exit('template not found — pass --template PATH')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('output', nargs='?', default='健康档案.html')
    ap.add_argument('--template', default=None)
    ap.add_argument('--data', default='data.json')
    ap.add_argument('--assets', default='assets.json')
    a = ap.parse_args()

    tpl = open(a.template or find_template(), encoding='utf-8').read()
    data = json.load(open(a.data, encoding='utf-8'))
    bundle = json.load(open(a.assets, encoding='utf-8'))

    for ph in ('/*__DATA__*/null', '/*__ASSETS__*/null', '/*__MANIFEST__*/null'):
        if ph not in tpl:
            sys.exit(f'template is missing placeholder {ph}')
    html = (tpl.replace('/*__DATA__*/null', js(data))
               .replace('/*__ASSETS__*/null', js(bundle['assets']))
               .replace('/*__MANIFEST__*/null', js(bundle['manifest'])))
    open(a.output, 'w', encoding='utf-8').write(html)

    mb = os.path.getsize(a.output) / 1048576
    nimg = sum(len(m.get('imgs', [])) for m in bundle['manifest']) \
        + sum(len(r.get('imgs', [])) for r in data['reports'])
    print(f'{a.output}  {mb:.1f} MB · {len(data["reports"])} reports · '
          f'{sum(len(p["items"]) for p in data.get("panels", []))} lab items · {nimg} images')


if __name__ == '__main__':
    main()
