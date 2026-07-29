#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""起点脚本：把抽出来的内容规整成 data.json。**复制到 workspace/ 再改。**

    cp starter/build_data.py workspace/
    cd workspace && python3 build_data.py

跟 build_assets.py 不同，这份**不可能自动跑通**——原始数据长什么样只有你知道。
它给的是骨架和正确的数据结构，你把 EXTRACTED 换成真实抽取结果，剩下的机械转换它包了。

把 tools/extract.py 取到的文字、或你用 Read 读图读出来的数值，填进 EXTRACTED。
字段定义见 docs/DATA_CONTRACT.md，可运行的完整范例见 demo/make_demo.py。
"""
import json, os, sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from lib import cluster_dates, parse_ref, qual_flag                 # noqa: E402

PATIENT = {'name': 'TODO 姓名', 'sex': 'TODO', 'age': 0, 'hospital': 'TODO 医院'}

# ============================================================== 你要填的部分
# 每条 = 一次测量。这是最省事的中间形态（长表），下面会自动 pivot 成契约要的时间序列。
# `flag` 填**报告上印的** ↑↓ 或异常标记，报告没标就填 None——不要自己按区间算，
# 那正是 tools/verify.py 要拿来跟你的区间对撞的东西（交叉校验）。
#
# ⚠ 参考区间**逐次填**，别图省事只填一次（坑 §4.3）。实验室会改判读标准，
#   同一个数值在新旧标准下结论可能相反。
EXTRACTED = [
    # (报告no, 日期,        面板,     项目名,       结果文本, 单位,     参考区间原文, 报告印的flag)
    ('01', '2026-01-20', '血常规', '白细胞计数', '6.12', '10^9/L', '3.5-9.5', None),
    ('01', '2026-01-20', '血常规', '血红蛋白', '112', 'g/L', '115-150', 'L'),
    ('02', '2026-01-20', '尿常规', '尿隐血', '+', '', '阴性', None),
    # TODO 换成你的真实抽取结果
]

# 每份报告的元信息。type 决定时间轴分行与报告库筛选项。
REPORT_META = [
    # (no,  日期,          名称,     类型,     结论,                            检查所见)
    ('01', '2026-01-20', '血常规', '检验报告', 'TODO 从报告正文抄结论', None),
    ('02', '2026-01-20', '尿常规', '检验报告', 'TODO', None),
    # TODO 影像类举例（status 会自动按「未见明显异常」判成「正常」，否则「见结论」）：
    # ('03', '2026-01-22', '甲状腺超声', '超声报告', '……结论原文……', '……检查所见原文……'),
]

PANEL_KEYS = {'血常规': 'cbc', '生化全套': 'chem', '尿常规': 'urine',
              '甲状腺功能': 'thyroid'}      # TODO 按你的面板补

# ====================================================== 下面一般不用改
def to_panels():
    """长表 → 契约要的「每项一条时间序列」（坑 §4.7：长表必须自己 pivot）。"""
    panels = OrderedDict()
    for no, date, panel, name, text, unit, ref, flag in EXTRACTED:
        p = panels.setdefault(panel, OrderedDict())
        p.setdefault(name, {'unit': unit, 'vals': []})
        lo, hi = parse_ref(ref)
        try:
            num = float(text)
        except (TypeError, ValueError):
            num = None
        # 定性项：报告没印箭头，按它自己印的参考标准补判（坑 §4.9，汇总表最爱漏这类）
        f = flag if flag else (qual_flag(text, ref) if num is None else None)
        p[name]['vals'].append({'d': date, 'v': num, 'f': f, 't': text,
                                'ref': ref, 'lo': lo, 'hi': hi, 'src': no})

    out = []
    for label, items in panels.items():
        dates = sorted({v['d'] for it in items.values() for v in it['vals']})
        built = []
        for name, it in items.items():
            vals = sorted(it['vals'], key=lambda v: v['d'])
            numeric = any(v['v'] is not None for v in vals)
            refs = {v['ref'] for v in vals}
            built.append({
                'name': name, 'unit': it['unit'],
                'ref': ' → '.join(sorted(refs)) if len(refs) > 1 else vals[-1]['ref'],
                'refVaries': len(refs) > 1,          # 表格会加 * 注释
                'lo': vals[-1]['lo'], 'hi': vals[-1]['hi'],   # 量程条用最近一次的区间
                'numeric': numeric, 'vals': vals,
                'abn': any(v['f'] for v in vals), 'abnLatest': bool(vals[-1]['f']),
                # TODO 想分组的话加 'group': '白细胞系'，并在下面 groups 里列出顺序
            })
        out.append({'key': PANEL_KEYS.get(label, label), 'label': label, 'dates': dates,
                    'groups': None, 'numericCount': sum(1 for b in built if b['numeric']),
                    'items': built})
    return out


def abn_of(panels, src):
    return [{'name': it['name'], 't': v['t'], 'f': v['f'], 'ref': v['ref'], 'unit': it['unit']}
            for p in panels for it in p['items'] for v in it['vals']
            if v['src'] == src and v['f']]


def to_reports(panels):
    out = []
    for no, date, name, rtype, conclusion, findings in REPORT_META:
        ab = abn_of(panels, no)
        if rtype == '检验报告':
            status = '异常' if ab else '正常'
        else:
            status = '正常' if '未见明显异常' in conclusion else '见结论'
        r = {'no': no, 'seq': int(no), 'date': date, 'name': name, 'type': rtype,
             'conclusion': conclusion, 'status': status, 'file': f'{no}_{name}.pdf',
             'sources': [{'no': no, 'file': f'{no}_{name}.pdf', 'name': name}],
             'exams': [name], 'merged': 1, 'tw': [], 'imgs': [], 'abnItems': ab}
        if findings:
            r['findings'] = findings
        out.append(r)
    # TODO 合并会话（坑 §4.2）：一次超声做了好几项、医院只出一份报告、导出却按项各存一份。
    #   把它们并成**一条**，sources[] 放各自的 PDF，exams[] 放各项检查名，merged=项数。
    #   判据是「同一天 + 所见与结论完全相同」，别按文件名判。
    # TODO 挂图：图直接属于这份报告就填 imgs=[{'k':'md01_0','cap':'…'}]；
    #   图在一份独立的图文报告文档里就填 tw=['tw00']。两种都行，图库会自己收集。
    return sorted(out, key=lambda r: (r['date'], r['no']))


def main():
    panels = to_panels()
    reports = to_reports(panels)
    dates = sorted({v['d'] for p in panels for it in p['items'] for v in it['vals']})

    data = {
        'patient': PATIENT,
        'reports': reports,
        'panels': panels,
        # 坑 §4.8：一次体检的抽血和检查常分散在几天，不归并的话对比分析会拿两个
        # 不相干的日期比，结果 0 项。
        'clusters': cluster_dates(dates),
        # TODO 可选：结节分级随访。**只摘录报告结论里印着的分级**，不要自己判。
        # 'grades': [{'date':'2026-01-22','sys':'TI-RADS','grade':'3',
        #             'what':'甲状腺左叶结节','name':'甲状腺超声','report':'03'}],
        # TODO 可选：健康主线。读懂这个人之后手写的叙述，但**每一句都要能在报告原文里找到出处**，
        # 不要推断病情、不要给医学建议。
        # 'threads': [{'title':'…','icon':'🦋','note':'…（以上为报告结论摘录）','reports':['03']}],
        'galleryNote': 'TODO 如实说明哪些报告没有可提取的图、去哪看原件。',
        'footNotes': [
            {'label': '数据来源', 'text': 'TODO 数据是从哪来的、覆盖哪段时间。'},
            {'label': '数据核对', 'text': 'TODO 核对了什么、发现了什么、哪些没核对。'
                                          '读的人靠这句判断这份档案能信到什么程度。'},
        ],
    }
    with open('data.json', 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    n = sum(len(p['items']) for p in panels)
    print(f'data.json  {len(reports)} 份报告 · {len(panels)} 个面板 / {n} 项化验 · '
          f"{len(data['clusters'])} 个体检批次")
    print('接着跑：python3 ../build_html.py out/我的健康档案.html '
          '--data data.json --assets assets.json')
    print('然后：python3 ../tools/verify.py data.json assets.json out/我的健康档案.html')


if __name__ == '__main__':
    main()
