#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the demo dashboard from entirely fabricated data.

    python3 demo/make_demo.py            # → demo/data.json, demo/assets.json, demo/index.html

EVERYTHING HERE IS INVENTED. No real person, hospital, date, lab value, report text or
image. The persona is an anonymous「演示用户」; the pictures come from demo/gen_images.py
and carry a synthetic-data watermark; DATA.banner says so at the top of the page.

This file doubles as the runnable specification of docs/DATA_CONTRACT.md — every field
the template reads is populated at least once. It also deliberately reproduces the data
traps documented in docs/20-extract.md, so the demo page shows what handling them looks
like rather than only describing it:

  坑 §4.2  一次超声多项共用一份报告   → report 16 merges three exams / three source PDFs
  坑 §4.3  参考区间随时间变化         → 25-羟基维生素D switches to a ≥50 criterion in 2026
  坑 §4.4  影像 PDF 里常常没有影像图   → DR / CT / 心电 carry no extractable picture
  坑 §4.6  图文报告被复制成多个文件    → the tw00 document is reached under two aliases
  坑 §4.8  一次体检分散在好几天       → each visit spans two or three dates
  坑 §4.9  定性异常汇总表常漏标       → 尿隐血 '+' is flagged 'A' from the report's own ref
"""
import base64, io, json, os, re, subprocess, sys

import fitz
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from lib import webp_b64                                            # noqa: E402

HOSPITAL = '示例市第一人民医院'
# Sex and age are deliberately 未知: a demo record should not describe a person.
PATIENT = {'name': '演示用户', 'sex': '性别未知', 'age': '年龄未知', 'hospital': HOSPITAL}

# Three visits, each spread over several days — that is what 坑 §4.8 is about.
LAB = ['2024-03-11', '2025-04-08', '2026-06-15']
IMG = ['2024-03-13', '2025-04-10', '2026-06-17']
FOLLOW = '2026-06-22'          # the visit's second day


# ============================================================ PDF text drawing
# PyMuPDF ships a Simplified Chinese face ('china-s') but renders Latin in it at full
# width, which looks wrong next to numbers. Split each string into CJK and ASCII runs
# and draw each with the right font, advancing x by the measured width of the run.
def _runs(s):
    out, cur, wide = [], '', None
    for ch in s:
        w = ord(ch) > 127
        if wide is None or w == wide:
            cur += ch; wide = w
        else:
            out.append((cur, wide)); cur, wide = ch, w
    if cur:
        out.append((cur, wide))
    return out


def _font(is_cjk, bold):
    return 'china-s' if is_cjk else ('hebo' if bold else 'helv')


def text_w(s, size, bold=False):
    return sum(fitz.get_text_length(t, fontname=_font(c, bold), fontsize=size)
               for t, c in _runs(s))


def draw(page, x, y, s, size=9, color=(0, 0, 0), bold=False):
    """Draw one line of mixed CJK/Latin text; returns the x it ended at.

    There is no bold Simplified Chinese face built in, so bold CJK is faked by stroking
    the glyphs (render_mode 2 = fill + stroke) rather than by drawing the run twice.
    Overprinting would look identical but would put every bold string into the PDF's
    text layer twice — and these PDFs exist partly so extraction can be tested."""
    for txt, is_cjk in _runs(s):
        fn = _font(is_cjk, bold)
        kw = {'render_mode': 2, 'border_width': 0.6, 'stroke_opacity': 1} \
            if (bold and is_cjk) else {}
        page.insert_text((x, y), txt, fontsize=size, fontname=fn, color=color, **kw)
        x += fitz.get_text_length(txt, fontname=fn, fontsize=size)
    return x


def draw_wrapped(page, x, y, s, size, maxw, leading=13.5):
    """Wrap by measured width — CJK has no spaces to break on. Returns the next y."""
    for para in s.split('\n'):
        line = ''
        for ch in para:
            if text_w(line + ch, size) > maxw and line:
                draw(page, x, y, line, size); y += leading; line = ch
            else:
                line += ch
        draw(page, x, y, line, size); y += leading
    return y


W, H = 595, 842          # A4 in points
M = 46                   # page margin
GRAY = (0.42, 0.42, 0.42)


def _frame(page, title, no, date, extra=''):
    """Shared letterhead: hospital, document title, patient row, rules."""
    draw(page, M, 58, HOSPITAL, 15, bold=True)
    draw(page, M, 78, title, 12.5, color=(0.15, 0.15, 0.15))
    draw(page, W - M - text_w(f'报告编号 SY{no}{date.replace("-", "")}', 8), 58,
         f'报告编号 SY{no}{date.replace("-", "")}', 8, color=GRAY)
    page.draw_line(fitz.Point(M, 88), fitz.Point(W - M, 88), color=(0.1, 0.1, 0.1), width=1.1)
    # sex/age are de-identified strings here ('性别未知'), not values — so they carry
    # their own label and must not get a second one, nor the 岁 suffix.
    sex = PATIENT['sex'] if '未知' in str(PATIENT['sex']) else f"性别：{PATIENT['sex']}"
    age = PATIENT['age'] if '未知' in str(PATIENT['age']) else f"年龄：{PATIENT['age']}岁"
    row = f"姓名：{PATIENT['name']}    {sex}    {age}    检查日期：{date}"
    draw(page, M, 104, row + (f'    {extra}' if extra else ''), 9, color=(0.2, 0.2, 0.2))
    page.draw_line(fitz.Point(M, 112), fitz.Point(W - M, 112), color=GRAY, width=0.5)


def _sign_off(page, y, date):
    page.draw_line(fitz.Point(M, y), fitz.Point(W - M, y), color=GRAY, width=0.5)
    draw(page, M, y + 15, f'检验/检查者：（示例）    审核者：（示例）    报告时间：{date} 09:30',
         8, color=GRAY)
    draw(page, M, y + 28, '本报告为演示用合成文件，不对应任何真实个人或医疗机构。', 8,
         color=(0.62, 0.3, 0.3))


def lab_pdf(no, date, title, rows):
    """A lab result sheet: 项目 / 结果 / 单位 / 参考区间 / 提示, paginated."""
    doc = fitz.open()
    cols = [M, M + 168, M + 258, M + 330, M + 428, W - M - 34]
    head = ['项目', '结果', '单位', '参考区间', '提示']
    page = None
    y = 0
    for i, (name, val, unit, ref, flag) in enumerate(rows):
        if page is None or y > H - 118:
            if page is not None:
                _sign_off(page, H - 92, date)
            page = doc.new_page(width=W, height=H)
            _frame(page, title, no, date, '标本类型：静脉血' if '尿' not in title else '标本类型：尿液')
            y = 132
            for c, t in zip(cols, head):
                draw(page, c, y, t, 8.6, bold=True, color=(0.25, 0.25, 0.25))
            y += 6
            page.draw_line(fitz.Point(M, y), fitz.Point(W - M, y), color=GRAY, width=0.5)
            y += 15
        col = (0.78, 0.16, 0.16) if flag in ('H', 'A') else (
            (0.13, 0.36, 0.72) if flag == 'L' else (0, 0, 0))
        draw(page, cols[0], y, name, 8.6)
        draw(page, cols[1], y, val, 8.6, color=col, bold=bool(flag))
        draw(page, cols[2], y, unit, 8.6, color=(0.3, 0.3, 0.3))
        draw(page, cols[3], y, ref, 8.6, color=(0.3, 0.3, 0.3))
        draw(page, cols[4], y, {'H': '↑', 'L': '↓', 'A': '异常'}.get(flag, ''), 8.6, color=col)
        y += 14.4
    _sign_off(page, H - 92, date)
    out = doc.tobytes()
    doc.close()
    return out


def imaging_pdf(no, date, title, exam, findings, conclusion, note=''):
    """An imaging report sheet: 检查所见 + 诊断意见."""
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    _frame(page, title, no, date, f'检查部位：{exam}')
    y = 140
    draw(page, M, y, '检查所见', 10, bold=True); y += 18
    y = draw_wrapped(page, M, y, findings, 9.2, W - 2 * M) + 12
    draw(page, M, y, '诊断意见', 10, bold=True); y += 18
    y = draw_wrapped(page, M, y, conclusion, 9.2, W - 2 * M) + 12
    if note:
        y = draw_wrapped(page, M, y, note, 8.4, W - 2 * M)
    _sign_off(page, H - 92, date)
    out = doc.tobytes()
    doc.close()
    return out


# ================================================================= lab panels
def series(name, unit, ref, lo, hi, vals, group=None, refs=None):
    """One lab item as a time series. `refs` overrides (ref, lo, hi) per visit — that
    is 坑 §4.3: the range belongs to the measurement, not to the item."""
    out = []
    for i, v in enumerate(vals):
        r, l, h = (refs[i] if refs else (ref, lo, hi))
        f = None
        if v is not None:
            if h is not None and v > h: f = 'H'
            elif l is not None and v < l: f = 'L'
        out.append({'d': LAB[i], 'v': v, 'f': f, 't': f'{v:g}', 'ref': r,
                    'lo': l, 'hi': h, 'src': None})       # src filled in once nos exist
    it = {'name': name, 'unit': unit, 'ref': ref, 'refVaries': bool(refs) and
          len({r[0] for r in refs}) > 1, 'lo': lo, 'hi': hi, 'vals': out, 'numeric': True,
          'abn': any(v['f'] for v in out), 'abnLatest': bool(out[-1]['f'])}
    if group:
        it['group'] = group
    return it


def qual(name, ref, texts, group=None, abnormal=lambda t: t.startswith('+')):
    """A qualitative item. Summary exports routinely miss these — 坑 §4.9 — so the flag
    is derived from the report's own reference wording, not from an arrow column."""
    out = [{'d': LAB[i], 'v': None, 'f': 'A' if abnormal(t) else None, 't': t,
            'ref': ref, 'lo': None, 'hi': None, 'src': None} for i, t in enumerate(texts)]
    it = {'name': name, 'unit': '', 'ref': ref, 'refVaries': False, 'lo': None, 'hi': None,
          'vals': out, 'numeric': False, 'abn': any(v['f'] for v in out),
          'abnLatest': bool(out[-1]['f'])}
    if group:
        it['group'] = group
    return it


CBC = ['白细胞系', '红细胞系', '血小板系']
cbc = {'key': 'cbc', 'label': '血常规', 'dates': LAB, 'groups': CBC, 'items': [
    series('白细胞计数', '10^9/L', '3.5-9.5', 3.5, 9.5, [6.12, 5.84, 7.02], CBC[0]),
    series('中性粒细胞百分比', '%', '40-75', 40, 75, [58.2, 61.4, 63.1], CBC[0]),
    series('淋巴细胞百分比', '%', '20-50', 20, 50, [32.1, 29.8, 27.4], CBC[0]),
    series('单核细胞百分比', '%', '3-10', 3, 10, [6.4, 5.9, 6.8], CBC[0]),
    series('嗜酸性粒细胞百分比', '%', '0.4-8.0', 0.4, 8.0, [2.1, 2.6, 2.2], CBC[0]),
    series('嗜碱性粒细胞百分比', '%', '0-1', 0, 1, [0.5, 0.4, 0.5], CBC[0]),
    series('中性粒细胞绝对值', '10^9/L', '1.8-6.3', 1.8, 6.3, [3.56, 3.59, 4.43], CBC[0]),
    series('淋巴细胞绝对值', '10^9/L', '1.1-3.2', 1.1, 3.2, [1.96, 1.74, 1.92], CBC[0]),
    series('红细胞计数', '10^12/L', '3.8-5.1', 3.8, 5.1, [4.42, 4.35, 4.28], CBC[1]),
    series('血红蛋白', 'g/L', '115-150', 115, 150, [132, 128, 112], CBC[1]),
    series('红细胞压积', '%', '35-45', 35, 45, [39.8, 38.6, 34.1], CBC[1]),
    series('平均红细胞体积', 'fL', '82-100', 82, 100, [90.1, 88.7, 81.4], CBC[1]),
    series('平均血红蛋白量', 'pg', '27-34', 27, 34, [29.9, 29.4, 27.6], CBC[1]),
    series('平均血红蛋白浓度', 'g/L', '316-354', 316, 354, [332, 331, 326], CBC[1]),
    series('红细胞分布宽度', '%', '11.5-14.5', 11.5, 14.5, [12.8, 13.1, 14.9], CBC[1]),
    series('血小板计数', '10^9/L', '125-350', 125, 350, [226, 241, 268], CBC[2]),
    series('平均血小板体积', 'fL', '7.6-13.2', 7.6, 13.2, [10.2, 10.5, 10.1], CBC[2]),
    series('血小板压积', '%', '0.108-0.282', 0.108, 0.282, [0.231, 0.253, 0.271], CBC[2]),
]}

CH = ['肝功能', '肾功能', '血脂', '电解质']
chem = {'key': 'chem', 'label': '生化全套', 'dates': LAB, 'groups': CH, 'items': [
    series('谷丙转氨酶', 'U/L', '7-40', 7, 40, [18, 22, 31], CH[0]),
    series('谷草转氨酶', 'U/L', '13-35', 13, 35, [20, 21, 24], CH[0]),
    series('碱性磷酸酶', 'U/L', '35-100', 35, 100, [62, 66, 71], CH[0]),
    series('γ-谷氨酰转肽酶', 'U/L', '7-45', 7, 45, [21, 26, 38], CH[0]),
    series('总胆红素', 'μmol/L', '3.4-20.5', 3.4, 20.5, [11.2, 10.4, 9.8], CH[0]),
    series('直接胆红素', 'μmol/L', '0-6.8', 0, 6.8, [3.1, 2.9, 2.8], CH[0]),
    series('总蛋白', 'g/L', '65-85', 65, 85, [73.2, 72.1, 71.4], CH[0]),
    series('白蛋白', 'g/L', '40-55', 40, 55, [45.1, 44.2, 43.0], CH[0]),
    series('球蛋白', 'g/L', '20-35', 20, 35, [28.1, 27.9, 28.4], CH[0]),
    series('尿素', 'mmol/L', '2.6-7.5', 2.6, 7.5, [4.6, 4.9, 5.4], CH[1]),
    series('肌酐', 'μmol/L', '41-73', 41, 73, [58, 60, 63], CH[1]),
    series('尿酸', 'μmol/L', '155-357', 155, 357, [268, 291, 364], CH[1]),
    series('估算肾小球滤过率', 'mL/min', '≥90', 90, None, [102, 98, 94], CH[1]),
    series('总胆固醇', 'mmol/L', '3.1-5.7', 3.1, 5.7, [4.82, 5.31, 5.94], CH[2]),
    series('甘油三酯', 'mmol/L', '0.4-1.7', 0.4, 1.7, [1.12, 1.48, 1.92], CH[2]),
    series('高密度脂蛋白胆固醇', 'mmol/L', '1.16-1.55', 1.16, 1.55, [1.48, 1.36, 1.21], CH[2]),
    series('低密度脂蛋白胆固醇', 'mmol/L', '≤3.37', None, 3.37, [2.76, 3.21, 3.82], CH[2]),
    series('载脂蛋白A1', 'g/L', '1.0-1.6', 1.0, 1.6, [1.42, 1.35, 1.28], CH[2]),
    series('载脂蛋白B', 'g/L', '0.6-1.1', 0.6, 1.1, [0.82, 0.91, 1.06], CH[2]),
    series('钾', 'mmol/L', '3.5-5.3', 3.5, 5.3, [4.21, 4.08, 4.32], CH[3]),
    series('钠', 'mmol/L', '137-147', 137, 147, [141, 140, 142], CH[3]),
    series('氯', 'mmol/L', '99-110', 99, 110, [104, 103, 105], CH[3]),
    series('钙', 'mmol/L', '2.11-2.52', 2.11, 2.52, [2.34, 2.31, 2.28], CH[3]),
]}

urine = {'key': 'urine', 'label': '尿常规', 'dates': LAB, 'groups': None, 'items': [
    series('尿比重', '', '1.003-1.030', 1.003, 1.030, [1.018, 1.020, 1.015]),
    series('尿酸碱度', '', '4.5-8.0', 4.5, 8.0, [6.0, 6.5, 5.5]),
    qual('尿蛋白', '阴性', ['-', '-', '-']),
    qual('尿糖', '阴性', ['-', '-', '-']),
    qual('尿隐血', '阴性', ['-', '-', '+']),
    qual('尿酮体', '阴性', ['-', '-', '-']),
    qual('尿胆原', '阴性', ['-', '-', '-']),
    qual('尿胆红素', '阴性', ['-', '-', '-']),
    qual('白细胞酯酶', '阴性', ['-', '-', '-']),
    qual('亚硝酸盐', '阴性', ['-', '-', '-']),
    series('尿白细胞', '/HP', '0-5', 0, 5, [2, 3, 4]),
    series('尿红细胞', '/HP', '0-3', 0, 3, [0, 1, 6]),
    series('上皮细胞', '/HP', '0-5', 0, 5, [2, 2, 3]),
]}

thyroid = {'key': 'thyroid', 'label': '甲状腺功能', 'dates': LAB, 'groups': None, 'items': [
    series('促甲状腺激素', 'mIU/L', '0.27-4.20', 0.27, 4.20, [2.14, 2.86, 3.42]),
    series('游离三碘甲状腺原氨酸', 'pmol/L', '3.1-6.8', 3.1, 6.8, [4.62, 4.48, 4.31]),
    series('游离甲状腺素', 'pmol/L', '12.0-22.0', 12.0, 22.0, [15.8, 15.2, 14.9]),
    series('甲状腺过氧化物酶抗体', 'IU/mL', '≤34', None, 34, [12.4, 28.6, 46.2]),
    series('甲状腺球蛋白抗体', 'IU/mL', '≤115', None, 115, [22.1, 35.4, 58.9]),
]}

# 坑 §4.3 lives here: the lab retired the old 12.3–107.0 window in 2026 and switched to a
# ≥50 sufficiency criterion. A summary sheet that keeps one range per item would either
# mis-flag the early values or miss the late one. Storing the range per measurement makes
# the question disappear, and the template draws the reference band in segments.
VITD_REFS = [('12.3-107.0', 12.3, 107.0), ('12.3-107.0', 12.3, 107.0), ('≥50', 50, None)]
special = {'key': 'special', 'label': '专项检查', 'dates': LAB, 'groups': None, 'items': [
    series('糖化血红蛋白', '%', '4.0-6.0', 4.0, 6.0, [5.2, 5.5, 5.9]),
    series('空腹血糖', 'mmol/L', '3.9-6.1', 3.9, 6.1, [5.12, 5.38, 5.86]),
    series('25-羟基维生素D', 'ng/mL', '12.3-107.0 → ≥50', 50, None,
           [26.5, 22.1, 31.8], refs=VITD_REFS),
    series('同型半胱氨酸', 'μmol/L', '≤15', None, 15, [9.2, 10.4, 12.8]),
    series('超敏C反应蛋白', 'mg/L', '≤3.0', None, 3.0, [0.8, 1.1, 1.6]),
]}

PANELS = [cbc, chem, urine, thyroid, special]
for p in PANELS:
    p['numericCount'] = sum(1 for it in p['items'] if it['numeric'])

# Which report number carries each panel on each visit.
PANEL_SRC = {'cbc': ['01', '11', '20'], 'chem': ['02', '12', '21'],
             'urine': ['03', '13', '22'], 'thyroid': ['04', '14', '23'],
             'special': ['05', '15', '24']}
for p in PANELS:
    for it in p['items']:
        for i, v in enumerate(it['vals']):
            v['src'] = PANEL_SRC[p['key']][i]


def abn_of(src):
    """Deviating items on one report — feeds its status badge and 偏离项 chips."""
    return [{'name': it['name'], 't': v['t'], 'f': v['f'], 'ref': v['ref'], 'unit': it['unit']}
            for p in PANELS for it in p['items'] for v in it['vals']
            if v['src'] == src and v['f']]


def panel_rows(key, i):
    """The same numbers again, in the shape the printed PDF shows them."""
    p = next(x for x in PANELS if x['key'] == key)
    return [(it['name'], it['vals'][i]['t'], it['unit'], it['vals'][i]['ref'], it['vals'][i]['f'])
            for it in p['items']]


# =================================================================== reports
ASSETS, MANIFEST, PDFS = {}, [], {}


def add_report(no, date, name, rtype, conclusion, pdf, findings=None, status=None,
               sources=None, exams=None, tw=None, imgs=None):
    ab = abn_of(no)
    st = status or ('异常' if ab else '正常')
    r = {'no': no, 'seq': int(no), 'date': date, 'name': name, 'type': rtype,
         'conclusion': conclusion, 'status': st, 'file': f'{no}_{name}.pdf',
         'sources': sources or [{'no': no, 'file': f'{no}_{name}.pdf', 'name': name}],
         'exams': exams or [name], 'merged': len(exams) if exams else 1,
         'tw': tw or [], 'imgs': imgs or [], 'abnItems': ab}
    if findings:
        r['findings'] = findings
    PDFS[no] = pdf
    return r


LAB_TITLES = {'cbc': ('血常规', '血常规检验报告单'), 'chem': ('生化全套', '生化检验报告单'),
              'urine': ('尿常规', '尿液分析报告单'), 'thyroid': ('甲状腺功能', '免疫检验报告单'),
              'special': ('专项检查', '专项检验报告单')}
reports = []
for i in range(3):
    for key, nos in PANEL_SRC.items():
        short, title = LAB_TITLES[key]
        no = nos[i]
        ab = abn_of(no)
        concl = ('提示：' + '；'.join(f"{a['name']} {a['t']}{a['unit']}" for a in ab)
                 if ab else '本次所检项目均在参考区间内。')
        reports.append(add_report(
            no, LAB[i], short, '检验报告', concl,
            lab_pdf(no, LAB[i], title, panel_rows(key, i))))

# ---- visit 1 imaging ------------------------------------------------------
reports.append(add_report(
    '06', IMG[0], '甲状腺超声', '超声报告',
    '甲状腺左叶低回声结节，TI-RADS 3 类，建议定期复查。\n右叶未见明显异常。',
    imaging_pdf('06', IMG[0], '超声检查报告单', '甲状腺及颈部淋巴结',
                '甲状腺大小形态正常，包膜完整。左叶中部探及一枚低回声结节，'
                '大小约 5×4mm，边界清晰，形态规则，内部回声均匀，未见明显血流信号。'
                '右叶实质回声均匀，未见异常回声区。双侧颈部未见明显肿大淋巴结。',
                '甲状腺左叶低回声结节，TI-RADS 3 类，建议定期复查。\n右叶未见明显异常。'),
    findings='左叶中部低回声结节，约 5×4mm，边界清晰，形态规则。右叶实质回声均匀。',
    status='见结论',
    imgs=[{'k': 'us_thy_2024_a', 'cap': '甲状腺左叶 · 低回声结节'},
          {'k': 'us_thy_2024_b', 'cap': '甲状腺右叶 · 实质回声均匀'}]))

reports.append(add_report(
    '07', IMG[0], '颈动脉超声', '超声报告',
    '双侧颈动脉内中膜略增厚，未见明确斑块。\n椎动脉血流通畅。',
    imaging_pdf('07', IMG[0], '超声检查报告单', '双侧颈动脉及椎动脉',
                '双侧颈总动脉走行规则，管腔通畅，内中膜厚度约 0.9mm，未见明确斑块回声。'
                '颈内动脉起始段血流充盈良好，流速正常范围。双侧椎动脉管径对称，'
                '血流方向正常，频谱形态未见异常。',
                '双侧颈动脉内中膜略增厚，未见明确斑块。\n椎动脉血流通畅。'),
    findings='双侧颈总动脉内中膜厚度约 0.9mm，未见明确斑块回声。椎动脉血流通畅。',
    status='见结论',
    imgs=[{'k': 'us_car_2024_a', 'cap': '颈总动脉长轴 · 内中膜测量'},
          {'k': 'us_car_2024_b', 'cap': '颈内动脉 · 血流充盈良好'}]))

reports.append(add_report(
    '08', IMG[0], '腹部超声', '超声报告', '肝、胆、胰、脾、双肾未见明显异常。',
    imaging_pdf('08', IMG[0], '超声检查报告单', '肝胆胰脾及双肾',
                '肝脏大小形态正常，实质回声均匀，肝内血管走行清晰。胆囊壁不厚，'
                '腔内未见异常回声。胰腺、脾脏未见异常。双肾大小形态正常，'
                '集合系统未见分离。',
                '肝、胆、胰、脾、双肾未见明显异常。'), status='正常'))

reports.append(add_report(
    '09', IMG[0], '胸部正侧位DR', '放射报告', '双肺未见明显活动性病变，心影不大。',
    imaging_pdf('09', IMG[0], 'X线检查报告单', '胸部正侧位',
                '双肺纹理清晰，未见明显斑片状高密度影。肺门不大，纵隔居中。'
                '心影大小形态正常。双侧膈面光整，肋膈角锐利。',
                '双肺未见明显活动性病变，心影不大。',
                '注：本报告 PDF 内嵌图片仅为机构标识与二维码，无可提取的诊断图像。'),
    status='正常'))

reports.append(add_report(
    '10', IMG[0], '心电图', '心电报告', '窦性心律，正常心电图。',
    imaging_pdf('10', IMG[0], '心电图检查报告单', '常规十二导联心电图',
                '窦性心律，心率 72 次/分，P-R 间期 0.16s，QRS 时限 0.08s，'
                'ST-T 未见明显异常。',
                '窦性心律，正常心电图。',
                '注：心电波形在原始 PDF 中为矢量图形，无法作为位图提取，请查看页面渲染图。'),
    status='正常'))

# ---- visit 2 imaging: one session, three exams, one shared 图文 document -----
# 坑 §4.2 — the hospital issued a single ultrasound session covering three exams and the
# export saved the identical conclusion under three file names. They merge into one report
# whose sources[] keeps all three PDFs, so nothing is lost and nothing is triplicated.
US2 = [('16', '甲状腺＋颈部淋巴结超声'), ('17', '颈动脉＋椎动脉超声'), ('18', '肝胆胰脾＋双肾超声')]
US2_CONCL = ('甲状腺左叶低回声结节，TI-RADS 3 类，较前变化不明显。\n'
             '双侧颈动脉内中膜增厚，右侧见一枚扁平斑块。\n'
             '肝、胆、胰、脾、双肾未见明显异常。')
US2_FIND = ('甲状腺左叶中部低回声结节，大小约 6×4mm，边界清晰，形态规则。'
            '双侧颈动脉内中膜厚度约 1.0mm，右侧颈总动脉分叉处见一枚扁平斑块，'
            '大小约 8×1.6mm，管腔未见明显狭窄。肝胆胰脾及双肾未见异常回声。')
for no, exam in US2:
    PDFS[no] = imaging_pdf(no, IMG[1], '超声检查报告单', exam, US2_FIND, US2_CONCL,
                           '注：本次超声共 3 项检查，医院出具一份合并报告，'
                           '导出时按检查项各存一份，正文完全相同。')
reports.append(add_report(
    '16', IMG[1], '超声检查 · 甲状腺、颈动脉、腹部', '超声报告', US2_CONCL, PDFS['16'],
    findings=US2_FIND, status='见结论',
    sources=[{'no': n, 'file': f'{n}_{e}.pdf', 'name': e} for n, e in US2],
    exams=[e for _, e in US2], tw=['tw00']))

reports.append(add_report(
    '19', IMG[1], '胸部低剂量CT', '放射报告',
    '右肺上叶微小结节（约 2mm），Lung-RADS 2 类，建议年度随访。\n余双肺未见明显异常。',
    imaging_pdf('19', IMG[1], 'CT检查报告单', '胸部低剂量螺旋CT',
                '双肺纹理清晰。右肺上叶尖段见一枚微小结节影，直径约 2mm，边缘光整，'
                '密度均匀。余肺野未见明显异常密度影。纵隔内未见肿大淋巴结。'
                '双侧胸膜未见增厚，胸腔未见积液。',
                '右肺上叶微小结节（约 2mm），Lung-RADS 2 类，建议年度随访。\n'
                '余双肺未见明显异常。',
                '注：本报告 PDF 无可提取的诊断图像，胶片需到影像科自助机打印。'),
    status='见结论'))

# ---- visit 3 imaging ------------------------------------------------------
reports.append(add_report(
    '25', IMG[2], '甲状腺超声', '超声报告',
    '甲状腺左叶低回声结节，较前增大，TI-RADS 4a 类，建议专科门诊就诊。\n'
    '右叶另见一枚微小结节，TI-RADS 3 类。',
    imaging_pdf('25', IMG[2], '超声检查报告单', '甲状腺及颈部淋巴结',
                '甲状腺左叶中部低回声结节，大小约 9×7mm（前次约 6×4mm），边界欠清，'
                '形态欠规则，内部回声不均，可见点状强回声，周边探及少许血流信号。'
                '右叶下极另见一枚低回声结节，大小约 3×3mm，边界清晰。'
                '双侧颈部未见明显肿大淋巴结。',
                '甲状腺左叶低回声结节，较前增大，TI-RADS 4a 类，建议专科门诊就诊。\n'
                '右叶另见一枚微小结节，TI-RADS 3 类。'),
    findings='左叶结节约 9×7mm，边界欠清，形态欠规则，内部回声不均，可见点状强回声。',
    status='见结论',
    imgs=[{'k': 'us_thy_2026_a', 'cap': '甲状腺左叶 · 结节较前增大'},
          {'k': 'us_thy_2026_b', 'cap': '甲状腺右叶 · 微小结节'}]))

reports.append(add_report(
    '26', IMG[2], '颈动脉超声', '超声报告',
    '双侧颈动脉内中膜增厚，右侧颈总动脉分叉处斑块较前略增大。\n管腔未见明显狭窄。',
    imaging_pdf('26', IMG[2], '超声检查报告单', '双侧颈动脉及椎动脉',
                '双侧颈动脉内中膜厚度约 1.1mm。右侧颈总动脉分叉处扁平斑块，'
                '大小约 11×1.8mm（前次约 8×1.6mm），表面尚光整，管腔未见明显狭窄。'
                '左侧未见明确斑块。双侧椎动脉血流通畅。',
                '双侧颈动脉内中膜增厚，右侧颈总动脉分叉处斑块较前略增大。\n'
                '管腔未见明显狭窄。'),
    findings='右侧颈总动脉分叉处扁平斑块约 11×1.8mm，表面尚光整，管腔未见明显狭窄。',
    status='见结论',
    imgs=[{'k': 'us_car_2026_a', 'cap': '右颈总动脉分叉 · 扁平斑块'}]))

# 坑 §4.4 in the flesh — a real CT report PDF carries no extractable picture, so this
# report has none either, and DATA.galleryNote explains the absence instead of hiding it.
reports.append(add_report(
    '27', IMG[2], '胸部低剂量CT', '放射报告',
    '右肺上叶结节较前增大（约 5mm），Lung-RADS 3 类，建议 6 个月复查。\n'
    '余双肺未见明显异常。',
    imaging_pdf('27', IMG[2], 'CT检查报告单', '胸部低剂量螺旋CT',
                '右肺上叶尖段结节影，直径约 5mm（前次约 2mm），边缘光整，密度均匀，'
                '未见分叶及毛刺。余肺野未见新发结节。纵隔内未见肿大淋巴结。'
                '双侧胸膜未见增厚，胸腔未见积液。',
                '右肺上叶结节较前增大（约 5mm），Lung-RADS 3 类，建议 6 个月复查。\n'
                '余双肺未见明显异常。',
                '注：本报告 PDF 无可提取的诊断图像，胶片需到影像科自助机打印。'),
    status='见结论'))

reports.append(add_report(
    '28', FOLLOW, '胸部正侧位DR', '放射报告', '双肺未见明显活动性病变，心影不大。',
    imaging_pdf('28', FOLLOW, 'X线检查报告单', '胸部正侧位',
                '双肺纹理清晰，未见明显斑片状高密度影。肺门不大，纵隔居中。'
                '心影大小形态正常。双侧膈面光整，肋膈角锐利。与两年前片对比未见明显变化。',
                '双肺未见明显活动性病变，心影不大。',
                '注：本报告 PDF 内嵌图片仅为机构标识与二维码，无可提取的诊断图像。'),
    status='正常'))

reports.append(add_report(
    '29', FOLLOW, '心电图', '心电报告', '窦性心律，正常心电图。',
    imaging_pdf('29', FOLLOW, '心电图检查报告单', '常规十二导联心电图',
                '窦性心律，心率 68 次/分，P-R 间期 0.15s，QRS 时限 0.08s，'
                'ST-T 未见明显异常。',
                '窦性心律，正常心电图。',
                '注：心电波形在原始 PDF 中为矢量图形，无法作为位图提取，请查看页面渲染图。'),
    status='正常'))

reports.sort(key=lambda r: (r['date'], r['no']))
for i, r in enumerate(reports, 1):
    r['seq'] = i

# ---- the 图文 document shared by the merged visit-2 session ------------------
# 坑 §4.6 — one document, saved once per exam name. Dedup by content hash, then keep the
# names it arrived under in `aliases` so the user can still find it by the name they know.
PDFS['tw00'] = imaging_pdf('tw00', IMG[1], '超声图文报告', '甲状腺、颈动脉、腹部',
                           '本图文报告包含本次超声检查的留图。', '见各项超声报告结论。',
                           '注：同一份图文报告在导出包中按检查项各存了一份，内容完全相同。')
TW_IMGS = [('us_thy_2025_a', '甲状腺左叶 · 第 1/4 张'), ('us_thy_2025_b', '甲状腺右叶 · 第 2/4 张'),
           ('us_car_2025_a', '右颈总动脉分叉 · 第 3/4 张'), ('us_abd_2025_a', '肝脏实质 · 第 4/4 张')]


# ==================================================================== assets
def build_assets():
    """Embed every document: raw base64 for download, WebP page renders for viewing."""
    for no, pdf_bytes in PDFS.items():
        ASSETS['pdf' + no] = base64.b64encode(pdf_bytes).decode()
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        pages = []
        for i, page in enumerate(doc):
            im = Image.open(io.BytesIO(page.get_pixmap(dpi=150).tobytes('png')))
            key = f'pg{no}_{i}'
            ASSETS[key] = webp_b64(im, width=900, quality=78)
            pages.append(key)
        doc.close()
        if no == 'tw00':
            MANIFEST.append({'kind': 'tw', 'no': 'tw00', 'file': '超声图文报告.pdf',
                             'pages': pages, 'exams': [e for _, e in US2],
                             'aliases': ['甲状腺_图文报告.pdf', '颈动脉_图文报告.pdf',
                                         '腹部_图文报告.pdf'],
                             'imgs': [{'k': k, 'cap': c} for k, c in TW_IMGS]})
        else:
            name = next((s['name'] for r in reports for s in r['sources'] if s['no'] == no), no)
            MANIFEST.append({'kind': 'report', 'no': no, 'file': f'{no}_{name}.pdf',
                             'pages': pages, 'imgs': []})

    for path in sorted(os.listdir(os.path.join(HERE, 'assets'))):
        if path.endswith('.webp'):
            with open(os.path.join(HERE, 'assets', path), 'rb') as fh:
                ASSETS[path[:-5]] = 'data:image/webp;base64,' + base64.b64encode(fh.read()).decode()


# ====================================================================== data
grades = [
    {'date': IMG[0], 'sys': 'TI-RADS', 'grade': '3', 'what': '甲状腺左叶结节',
     'name': '甲状腺超声', 'report': '06'},
    {'date': IMG[1], 'sys': 'TI-RADS', 'grade': '3', 'what': '甲状腺左叶结节',
     'name': '超声检查 · 甲状腺、颈动脉、腹部', 'report': '16'},
    {'date': IMG[2], 'sys': 'TI-RADS', 'grade': '4a', 'what': '甲状腺左叶结节',
     'name': '甲状腺超声', 'report': '25'},
    {'date': IMG[1], 'sys': 'Lung-RADS', 'grade': '2', 'what': '右肺上叶结节',
     'name': '胸部低剂量CT', 'report': '19'},
    {'date': IMG[2], 'sys': 'Lung-RADS', 'grade': '3', 'what': '右肺上叶结节',
     'name': '胸部低剂量CT', 'report': '27'},
]

clusters = [
    {'id': LAB[0], 'label': '2024年03月', 'dates': [LAB[0], IMG[0]],
     'span': f'{LAB[0]} ~ {IMG[0]}'},
    {'id': LAB[1], 'label': '2025年04月', 'dates': [LAB[1], IMG[1]],
     'span': f'{LAB[1]} ~ {IMG[1]}'},
    {'id': LAB[2], 'label': '2026年06月', 'dates': [LAB[2], IMG[2], FOLLOW],
     'span': f'{LAB[2]} ~ {FOLLOW}'},
]

# Every note below is a condensation of what the fabricated reports literally say. A
# thread is a reading aid, not an opinion — nothing here adds a judgement the reports
# did not print. Keep it that way when you write your own.
threads = [
    {'title': '甲状腺结节随访', 'icon': '🦋', 'reports': ['25', '16', '06'],
     'note': '左叶结节三次超声：2024 年 5×4mm、TI-RADS 3 类；2025 年 6×4mm、'
             '仍为 3 类；2026 年 9×7mm、报告改为 4a 类并建议专科门诊就诊。'
             '（以上为三份报告结论原文的摘录）'},
    {'title': '肺结节随访', 'icon': '🫁', 'reports': ['27', '19'],
     'note': '右肺上叶结节两次低剂量 CT：2025 年约 2mm、Lung-RADS 2 类、建议年度随访；'
             '2026 年约 5mm、报告改为 Lung-RADS 3 类并建议 6 个月复查。'
             '（以上为两份报告结论原文的摘录）'},
    {'title': '颈动脉斑块随访', 'icon': '🩺', 'reports': ['26', '16', '07'],
     'note': '2024 年颈动脉内中膜约 0.9mm、未见明确斑块；2025 年右侧分叉处出现扁平斑块'
             '约 8×1.6mm；2026 年斑块约 11×1.8mm，三次报告均记录管腔未见明显狭窄。'
             '（以上为三份报告结论原文的摘录）'},
    {'title': '血脂与代谢', 'icon': '🩸', 'reports': ['21', '24'],
     'note': '2026 年生化报告标注总胆固醇、甘油三酯、低密度脂蛋白胆固醇与尿酸四项偏高；'
             '同次专项检查的糖化血红蛋白 5.9%、空腹血糖 5.86mmol/L 仍在参考区间内。'
             '（以上为报告打印结果的摘录）'},
]

DATA = {
    'patient': PATIENT,
    'banner': {'title': '演示数据',
               'text': '本页的姓名、日期、化验数值、报告结论与全部图片均为程序合成的'
                       '虚构内容，不对应任何真实个人、医疗机构或医学影像。'},
    'reports': reports, 'panels': PANELS, 'grades': grades,
    'clusters': clusters, 'threads': threads,
    'galleryNote': '以下图片全部来自超声报告——真实导出包里也是这样：胸部 DR、胸部低剂量 CT '
                   '与心电图的 PDF 内嵌的只有机构标识与二维码（心电波形是矢量图形，没有位图可提），'
                   '所以这些报告在图库里不出现。要看它们请到「报告库」打开对应报告的页面渲染图。'
                   '全部图片均为合成示意图，非真实医疗影像。',
    'footNotes': [
        {'label': '数据来源', 'text': '全部为虚构的合成数据，由 demo/make_demo.py 生成，'
                                      '任何人都可以重新跑一遍复现这个页面。'},
        {'label': '关于参考区间', 'text': '25-羟基维生素D 的判读标准在 2026 年从 '
                                          '12.3–107.0 改为「≥50 为充足」。表格里带 * 的项目'
                                          '表示各次参考区间不一致，趋势图按每次自己的区间'
                                          '分段画参考带——同一个数值在新旧标准下结论不同，'
                                          '这正是要逐次保存参考区间的原因。'},
        {'label': '数据核对', 'text': '演示数据无需核对。处理真实报告时请跑 '
                                      'tools/verify.py 做交叉校验，并把核对结论写在这里——'
                                      '读的人才知道这份档案能信到什么程度。'},
    ],
}


def main():
    build_assets()
    data_p = os.path.join(HERE, 'data.json')
    assets_p = os.path.join(HERE, 'assets.json')
    out_p = os.path.join(HERE, 'index.html')
    with open(data_p, 'w', encoding='utf-8') as fh:
        json.dump(DATA, fh, ensure_ascii=False, indent=1)
    with open(assets_p, 'w', encoding='utf-8') as fh:
        json.dump({'assets': ASSETS, 'manifest': MANIFEST}, fh, ensure_ascii=False)

    subprocess.run([sys.executable, os.path.join(ROOT, 'build_html.py'), out_p,
                    '--data', data_p, '--assets', assets_p], check=True)
    n_items = sum(len(p['items']) for p in PANELS)
    n_imgs = sum(len(r['imgs']) for r in reports) + len(TW_IMGS)
    print(f'demo: {len(reports)} reports · {len(PANELS)} panels / {n_items} lab items · '
          f'{n_imgs} images · {len(PDFS)} documents · all synthetic')


if __name__ == '__main__':
    main()
