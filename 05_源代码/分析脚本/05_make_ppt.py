# -*- coding: utf-8 -*-
"""
生成汇报用 PPT（16 页，深色主题，匹配可视化大屏的配色）。

运行：
    python analysis/05_make_ppt.py

依赖：python-pptx、Pillow（本机 PyCharm 的 .venv 里若没有，可用系统 Python 运行；
      脚本本身只读文件、写一个 .pptx，不碰数据库）。

想改内容：直接改下面 SLIDES 相关的函数即可，每个 build_xxx() 对应一页。
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from lxml import etree
from PIL import Image

# ---------------------------------------------------------------- 路径
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
IMG = {
    "dash":  os.path.join(PROJ, "web", "预览截图.png"),
    "fig1":  os.path.join(HERE, "model_output", "fig1_boundary.png"),
    "fig2":  os.path.join(HERE, "model_output", "fig2_confusion.png"),
    "fig3":  os.path.join(HERE, "model_output", "fig3_features.png"),
    "fig4":  os.path.join(HERE, "model_output", "fig4_length.png"),
    "fig5":  os.path.join(HERE, "model_output", "fig5_genre.png"),
}
OUT = os.path.join(PROJ, "豆瓣影视数据项目_汇报.pptx")

# ---------------------------------------------------------------- 配色（与大屏一致）
BG    = RGBColor(0x0F, 0x17, 0x2A)   # 深蓝底
CARD  = RGBColor(0x1E, 0x29, 0x3B)   # 卡片
LINE  = RGBColor(0x33, 0x41, 0x55)   # 分隔线
CYAN  = RGBColor(0x22, 0xD3, 0xEE)   # 主色
PINK  = RGBColor(0xF4, 0x72, 0xB6)   # 副色（差评/风险）
GOLD  = RGBColor(0xFB, 0xBF, 0x24)   # 强调
TEXT  = RGBColor(0xE2, 0xE8, 0xF0)   # 正文
MUTED = RGBColor(0x94, 0xA3, 0xB8)   # 次要文字
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT  = "微软雅黑"

SW, SH = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.85)
CW = SW - MARGIN * 2                  # 内容宽度 11.633"


# ---------------------------------------------------------------- 基础工具
def set_run(run, size, color, bold=False, font=FONT):
    """设置一段文字的字号/颜色/粗体，并强制中文字体（否则可能回落到宋体）。"""
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font                      # a:latin
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):              # 中文（东亚）+ 复杂脚本
        el = rPr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rPr, qn(tag))
        el.set("typeface", font)


def new_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])   # 6 = 空白版式
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s


def rect(slide, l, t, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE, line_w=1.0):
    sh = slide.shapes.add_shape(shape, l, t, w, h)
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    return sh


def add_text(slide, l, t, w, h, paras, anchor=MSO_ANCHOR.TOP):
    """paras: 每项是 dict，字段：
       runs=[(文本, 字号, 颜色, 粗体), ...]  或  t='纯文本'（配合 size/color/bold）
       align / space_after / space_before / line_spacing
    """
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = p.get("align", PP_ALIGN.LEFT)
        para.line_spacing = p.get("line_spacing", 1.25)
        if p.get("space_before"):
            para.space_before = Pt(p["space_before"])
        if p.get("space_after") is not None:
            para.space_after = Pt(p["space_after"])
        runs = p.get("runs") or [(p.get("t", ""), p.get("size", 15),
                                  p.get("color", TEXT), p.get("bold", False))]
        for txt, size, color, bold in runs:
            r = para.add_run()
            r.text = txt
            set_run(r, size, color, bold)
    return tb


def header(slide, kicker, title, sub=None):
    """统一页头：左侧青色竖条 + 小标签 + 大标题。"""
    rect(slide, MARGIN, Inches(0.52), Inches(0.06), Inches(0.78), fill=CYAN)
    add_text(slide, MARGIN + Inches(0.22), Inches(0.5), CW - Inches(0.3), Inches(0.3),
             [{"t": kicker, "size": 13, "color": CYAN, "bold": True}])
    add_text(slide, MARGIN + Inches(0.22), Inches(0.74), CW - Inches(0.3), Inches(0.5),
             [{"t": title, "size": 28, "color": WHITE, "bold": True}])
    y = Inches(1.42)
    if sub:
        add_text(slide, MARGIN, y, CW, Inches(0.3),
                 [{"t": sub, "size": 13.5, "color": MUTED}])
        y = Inches(1.78)
    return y


def page_no(slide, n):
    add_text(slide, SW - Inches(1.1), SH - Inches(0.55), Inches(0.7), Inches(0.3),
             [{"t": str(n), "size": 11, "color": LINE, "align": PP_ALIGN.RIGHT}])


def bullets(slide, l, t, w, h, items, size=15, gap=10, color=TEXT, mark="•", mark_color=CYAN):
    """手动加项目符号（文本框不会自动加）。sub 项用 └ 缩进。"""
    paras = []
    for it in items:
        sub = it.startswith("~")
        txt = it[1:] if sub else it
        paras.append({
            "runs": [(("      └ " if sub else mark + "  "), size, mark_color, True),
                     (txt, size - (1 if sub else 0), color, False)],
            "space_after": gap,
            "line_spacing": 1.22,
        })
    return add_text(slide, l, t, w, h, paras)


def add_image_fit(slide, path, l, t, w, h, border=True):
    """按比例缩放居中放进 (l,t,w,h) 的框里，可选描边。"""
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    left = int(l + (w - nw) / 2)
    top = int(t + (h - nh) / 2)
    if border:
        rect(slide, left - Inches(0.04), top - Inches(0.04),
             nw + Inches(0.08), nh + Inches(0.08), fill=None, line=LINE, line_w=0.75)
    return slide.shapes.add_picture(path, left, top, width=nw, height=nh)


def add_table(slide, l, t, w, data, col_ratio, row_h=0.36, head_h=0.42,
              size=12, head_size=12.5, align_first_left=True,
              highlight_rows=(), head_color=CYAN):
    rows, cols = len(data), len(data[0])
    shp = slide.shapes.add_table(rows, cols, l, t, w, Inches(head_h + row_h * (rows - 1)))
    tbl = shp.table
    tbl.first_row = False       # 关掉主题自动样式，全部自己刷
    tbl.horz_banding = False
    total = sum(col_ratio)
    for i, r in enumerate(col_ratio):
        tbl.columns[i].width = int(w * r / total)
    for ri in range(rows):
        tbl.rows[ri].height = Inches(head_h if ri == 0 else row_h)
        for ci in range(cols):
            cell = tbl.cell(ri, ci)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.01)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if ri == 0:
                cell.fill.fore_color.rgb = RGBColor(0x15, 0x23, 0x38)
            elif ri in highlight_rows:
                cell.fill.fore_color.rgb = RGBColor(0x13, 0x3B, 0x45)
            else:
                cell.fill.fore_color.rgb = CARD if ri % 2 else RGBColor(0x18, 0x22, 0x35)

            tf = cell.text_frame
            tf.word_wrap = True
            para = tf.paragraphs[0]
            para.alignment = PP_ALIGN.LEFT if (ci == 0 and align_first_left) else PP_ALIGN.CENTER
            r = para.add_run()
            r.text = str(data[ri][ci])
            if ri == 0:
                set_run(r, head_size, head_color, True)
            elif ri in highlight_rows:
                set_run(r, size, WHITE, True)
            else:
                set_run(r, size, TEXT, False)
    return tbl


def kpi_card(slide, l, t, w, h, num, unit, label, note=None,
             num_color=CYAN):
    rect(slide, l, t, w, h, fill=CARD)
    rect(slide, l, t, w, Inches(0.045), fill=num_color)
    add_text(slide, l + Inches(0.28), t + Inches(0.24), w - Inches(0.5), Inches(0.75),
             [{"runs": [(num, 40, num_color, True), ("  " + unit, 14, MUTED, False)]}])
    add_text(slide, l + Inches(0.28), t + Inches(1.02), w - Inches(0.5), Inches(0.34),
             [{"t": label, "size": 14.5, "color": TEXT, "bold": True}])
    if note:
        add_text(slide, l + Inches(0.28), t + Inches(1.38), w - Inches(0.5), Inches(0.5),
                 [{"t": note, "size": 11.5, "color": MUTED, "line_spacing": 1.2}])


# ---------------------------------------------------------------- 各页
def s01_cover(prs):
    s = new_slide(prs)
    rect(s, Inches(0), Inches(0), SW, Inches(0.10), fill=CYAN)
    rect(s, Inches(0), Inches(0), Inches(4.6), Inches(0.10), fill=PINK)

    add_text(s, MARGIN, Inches(1.85), CW, Inches(0.4),
             [{"t": "数据采集与分析 · 课程项目汇报", "size": 15, "color": CYAN, "bold": True}])
    add_text(s, MARGIN, Inches(2.32), CW, Inches(1.5),
             [{"t": "豆瓣高分影视", "size": 52, "color": WHITE, "bold": True}],
             )
    add_text(s, MARGIN, Inches(3.28), CW, Inches(1.5),
             [{"t": "数据采集与文本分析", "size": 52, "color": WHITE, "bold": True}])
    add_text(s, MARGIN, Inches(4.44), CW, Inches(0.4),
             [{"t": "从写爬虫、做可视化大屏，到用短评文本预测星级的一次完整实践",
               "size": 17, "color": MUTED}])

    rect(s, MARGIN, Inches(5.18), Inches(3.4), Inches(0.03), fill=LINE)
    add_text(s, MARGIN, Inches(5.42), CW, Inches(0.9),
             [{"runs": [("1052", 20, CYAN, True), (" 部作品　", 13, MUTED, False),
                        ("4695", 20, CYAN, True), (" 条短评　", 13, MUTED, False),
                        ("9", 20, CYAN, True), (" 张大屏图表　", 13, MUTED, False),
                        ("7", 20, CYAN, True), (" 个模型对照", 13, MUTED, False)]}])
    add_text(s, MARGIN, Inches(6.28), CW, Inches(0.4),
             [{"t": "汇报人：＿＿＿＿＿　　班级：＿＿＿＿＿　　日期：＿＿＿＿＿＿",
               "size": 13, "color": MUTED}])
    return s


def s02_overview(prs):
    s = new_slide(prs)
    header(s, "OVERVIEW", "一页看懂这个项目",
           "四个阶段各自独立可复现：采集 → 清洗 → 可视化 → 建模")
    gap = Inches(0.28)
    w = (CW - gap * 3) / 4
    cards = [
        ("1052", "部", "高分影视作品", "候选池 1131 部\n电影 539 / 剧集 513"),
        ("4695", "条", "热门短评", "覆盖 939 部作品\n每部固定 5 条"),
        ("9", "张", "可视化大屏图表", "ECharts + HTML/CSS/JS\n离线双击即可演示"),
        ("7", "个", "模型横向对照", "5 折交叉验证\n全部指标 out-of-fold"),
    ]
    for i, (num, unit, lab, note) in enumerate(cards):
        kpi_card(s, MARGIN + i * (w + gap), Inches(2.05), w, Inches(2.05),
                 num, unit, lab, note, num_color=[CYAN, GOLD, PINK, CYAN][i])

    rect(s, MARGIN, Inches(4.55), CW, Inches(0.92), fill=CARD)
    rect(s, MARGIN, Inches(4.55), Inches(0.05), Inches(0.92), fill=GOLD)
    add_text(s, MARGIN + Inches(0.35), Inches(4.72), CW - Inches(0.7), Inches(0.6),
             [{"runs": [("一句话结论：", 16, GOLD, True),
                        ("短评文本里确实有“态度”信息，但弱得不足以做实用分类器——"
                         "最好的模型 AUC 0.647、准确率 60.6%，只比“全猜 5 星”高 3.1 个百分点。",
                         16, TEXT, False)], "line_spacing": 1.3}])
    page_no(s, 2)
    return s


def s03_stages(prs):
    s = new_slide(prs)
    header(s, "WORKFLOW", "项目目标与四个阶段")
    stages = [
        ("①", "数据采集", "自己写爬虫抓豆瓣公开页面", "1052 部作品 + 4695 条短评", CYAN),
        ("②", "清洗与特征工程", "整理成能直接分析的宽表", "1052×60 列 / 4695×26 列", GOLD),
        ("③", "可视化大屏", "ECharts + HTML/CSS/JS", "9 张图 + 6 张 KPI 卡", PINK),
        ("④", "文本建模", "短评文本能否预测星级", "7 模型对照 + 6 张诊断图", CYAN),
    ]
    gap = Inches(0.26)
    w = (CW - gap * 3) / 4
    for i, (no, name, desc, out, c) in enumerate(stages):
        l = MARGIN + i * (w + gap)
        rect(s, l, Inches(1.95), w, Inches(2.6), fill=CARD)
        rect(s, l, Inches(1.95), w, Inches(0.05), fill=c)
        add_text(s, l + Inches(0.26), Inches(2.16), w - Inches(0.5), Inches(0.6),
                 [{"t": no, "size": 30, "color": c, "bold": True}])
        add_text(s, l + Inches(0.26), Inches(2.86), w - Inches(0.5), Inches(0.4),
                 [{"t": name, "size": 17, "color": WHITE, "bold": True}])
        add_text(s, l + Inches(0.26), Inches(3.30), w - Inches(0.5), Inches(0.7),
                 [{"t": desc, "size": 12.5, "color": MUTED, "line_spacing": 1.25}])
        add_text(s, l + Inches(0.26), Inches(3.98), w - Inches(0.5), Inches(0.4),
                 [{"t": out, "size": 12, "color": c}])
        if i < 3:
            add_text(s, l + w - Inches(0.02), Inches(3.0), Inches(0.3), Inches(0.4),
                     [{"t": "›", "size": 22, "color": LINE, "align": PP_ALIGN.CENTER}])

    add_text(s, MARGIN, Inches(4.85), CW, Inches(1.2),
             [{"runs": [("为什么值得做：", 15, GOLD, True),
                        ("豆瓣短评文本短、口语化、还天然带标签（星级），是练文本分类的理想数据；"
                         "但要真正回答“它能不能预测星级”，必须用交叉验证和基线把自己说服一遍。",
                         15, TEXT, False)], "line_spacing": 1.35}])
    add_text(s, MARGIN, Inches(5.6), CW, Inches(1.0),
             [{"t": "本项目最大的特点：最后一节的结论是否定性的 —— 我们没有停在“跑出 97% 准确率”就收工。",
               "size": 14, "color": PINK}])
    page_no(s, 3)
    return s


def s04_collect_scale(prs):
    s = new_slide(prs)
    header(s, "STEP 1 · 数据采集", "抓到了什么",
           "采集时间 2026-10-13 ~ 10-14，共约 1 天（含夜间连续运行）")
    gap = Inches(0.28)
    w = (CW - gap * 3) / 4
    cards = [
        ("1131", "部", "发现到的候选作品", "按类型 × 地区 × 年份\n的查询矩阵枚举出来"),
        ("1052", "部", "抓完整资料", "电影 539 / 剧集 513\n（豆瓣发现接口混在一起）"),
        ("942", "部", "连评分分布也抓到", "五星~一星占比\n五数之和全部≈100%"),
        ("4695", "条", "热门短评", "覆盖 939 部作品\n每部固定 5 条"),
    ]
    for i, (num, unit, lab, note) in enumerate(cards):
        kpi_card(s, MARGIN + i * (w + gap), Inches(2.05), w, Inches(2.0),
                 num, unit, lab, note, num_color=CYAN)

    rect(s, MARGIN, Inches(4.35), CW, Inches(1.5), fill=CARD)
    add_text(s, MARGIN + Inches(0.32), Inches(4.55), CW - Inches(0.64), Inches(1.1),
             [{"runs": [("为什么每部只有 5 条短评？", 14.5, GOLD, True),
                        ("　电脑端详情页每页只展示 5 条热门短评，想翻更多条立刻撞验证码墙；"
                         "所以本项目的数据定位是“每部作品的口碑样本”，不是全量短评库。",
                         14.5, TEXT, False)], "line_spacing": 1.35, "space_after": 8},
              {"runs": [("影响：", 14.5, PINK, True),
                        ("平均每部 4.9 条，“同一部电影内部”的统计会很不稳定，"
                         "这一点在建模阶段变成了一个重要的对照（见第 14 页）。", 14.5, TEXT, False)],
               "line_spacing": 1.35}])
    page_no(s, 4)
    return s


def s05_collect_method(prs):
    s = new_slide(prs)
    header(s, "STEP 1 · 数据采集", "怎么抓的：免登录 + 刻意放慢")
    items = [
        "免登录：全程只用公开页面，代码里没有任何账号密码、不需要 Cookie",
        "双通道：电脑端详情页（资料全、含评分分布）＋ 手机端接口（快，但拿不到五星占比）",
        "刻意放慢：每 9 次请求主动休息 180 秒，请求间隔 6~9 秒，约 2 部/分钟",
        "~为了快而调小间隔，一撞墙就是 2~3 分钟（验证码）甚至半小时（全站 403）的停摆，反而更慢",
        "断点续爬：所有进度落 SQLite，进程中断后重跑会自动跳过已完成的条目",
        "遇到 403 时换出口网络恢复，而不是硬刚 —— 一夜连跑期间失败 0 条、失效 0 条",
    ]
    bullets(s, MARGIN, Inches(1.85), CW, Inches(3.6), items, size=15.5, gap=13)

    rect(s, MARGIN, Inches(5.35), CW, Inches(1.15), fill=CARD)
    rect(s, MARGIN, Inches(5.35), Inches(0.05), Inches(1.15), fill=GOLD)
    add_text(s, MARGIN + Inches(0.35), Inches(5.55), CW - Inches(0.7), Inches(0.8),
             [{"runs": [("工程上的取舍：", 14.5, GOLD, True),
                        ("“慢”是主动设计的。整个采集过程里最贵的不是请求，而是被限流后的等待，"
                         "所以宁可把节奏写死在配置里。", 14.5, TEXT, False)], "line_spacing": 1.35}])
    page_no(s, 5)
    return s


def s06_quality(prs):
    s = new_slide(prs)
    header(s, "STEP 1 · 数据采集", "数据质量：自检全通过，缺口也说清楚")
    half = (CW - Inches(0.3)) / 2

    rect(s, MARGIN, Inches(1.85), half, Inches(3.9), fill=CARD)
    rect(s, MARGIN, Inches(1.85), half, Inches(0.05), fill=CYAN)
    add_text(s, MARGIN + Inches(0.3), Inches(2.08), half - Inches(0.6), Inches(0.4),
             [{"t": "质量自检（6 项全部通过）", "size": 16, "color": CYAN, "bold": True}])
    bullets(s, MARGIN + Inches(0.3), Inches(2.62), half - Inches(0.6), Inches(3.0), [
        "五星~一星占比之和偏离 100% 超过 1.2pp 的：0 部",
        "rating 与评分分布永远同进同退：0 例外",
        "短评正文 / 时间 / 作者空值：0 条",
        "每部短评条数 min = max = 5",
        "数据库 PRAGMA integrity_check = ok",
        "抽样与豆瓣页面逐字核对一致",
    ], size=12.5, gap=8)

    l2 = MARGIN + half + Inches(0.3)
    rect(s, l2, Inches(1.85), half, Inches(3.9), fill=CARD)
    rect(s, l2, Inches(1.85), half, Inches(0.05), fill=PINK)
    add_text(s, l2 + Inches(0.3), Inches(2.08), half - Inches(0.6), Inches(0.4),
             [{"t": "已知缺口（主动交代）", "size": 16, "color": PINK, "bold": True}])
    bullets(s, l2 + Inches(0.3), Inches(2.62), half - Inches(0.6), Inches(3.0), [
        "110 部有资料但没有评分分布（早期走手机端接口）",
        "189 部完全没抓完（候选池里排在后面）",
        "113 部有资料但没有短评（冷门条目页面没展示）",
        "短评每部只有 5 条（设计如此）",
        "9 部 fail_count=1，都是撞验证码墙留下的",
        "1052 部里只有 539 部是“电影”，513 部是剧集",
    ], size=12.5, gap=8, mark_color=PINK)

    add_text(s, MARGIN, Inches(5.95), CW, Inches(0.5),
             [{"t": "所有缺口都在《数据说明.md》里逐条写明，并给了补齐命令 —— 不藏问题。",
               "size": 13.5, "color": MUTED}])
    page_no(s, 6)
    return s


def s07_clean(prs):
    s = new_slide(prs)
    header(s, "STEP 2 · 清洗与特征工程", "从原始数据到两张分析表",
           "只用 Python 标准库，不依赖 pandas —— 打开就能跑")
    lw = Inches(5.3)
    rect(s, MARGIN, Inches(1.95), lw, Inches(3.5), fill=CARD)
    rect(s, MARGIN, Inches(1.95), lw, Inches(0.05), fill=CYAN)
    add_text(s, MARGIN + Inches(0.3), Inches(2.18), lw - Inches(0.6), Inches(0.5),
             [{"runs": [("analysis_movies.csv", 15, CYAN, True), ("　1052 × 60 列", 13, MUTED, False)]}])
    bullets(s, MARGIN + Inches(0.3), Inches(2.74), lw - Inches(0.6), Inches(2.6), [
        "类型：Top15 类型 one-hot + 类型数量",
        "时间：上映年份、年代分档（1950s~2020s）",
        "热度：评价人数取对数、分档",
        "口碑形态：good_rate / bad_rate / polarization / talk_ratio",
        "榜单：是否 Top250、具体名次",
        "短评聚合：条数、平均星、标准差、平均字数",
    ], size=12, gap=6)

    l2 = MARGIN + lw + Inches(0.3)
    w2 = CW - lw - Inches(0.3)
    rect(s, l2, Inches(1.95), w2, Inches(3.5), fill=CARD)
    rect(s, l2, Inches(1.95), w2, Inches(0.05), fill=GOLD)
    add_text(s, l2 + Inches(0.3), Inches(2.18), w2 - Inches(0.6), Inches(0.5),
             [{"runs": [("analysis_comments.csv", 15, GOLD, True), ("　4695 × 26 列", 13, MUTED, False)]}])
    bullets(s, l2 + Inches(0.3), Inches(2.74), w2 - Inches(0.6), Inches(2.6), [
        "content_clean：去链接 / @某人 / #话题#，只留中文数字字母",
        "文本形态：字数、感叹号、问号、省略号、emoji",
        "时间拆解：发表时间 → 年 / 月",
        "标签：label_top（5星 vs ≤4星）、label_pos（差评/中评/好评）",
    ], size=12, gap=7, mark_color=GOLD)

    rect(s, MARGIN, Inches(5.65), CW, Inches(1.05), fill=RGBColor(0x2A, 0x1E, 0x2E))
    add_text(s, MARGIN + Inches(0.35), Inches(5.82), CW - Inches(0.7), Inches(0.75),
             [{"runs": [("清洗时踩的两个坑：", 14, PINK, True),
                        ("① SQLite 里 year / votes 存的是文本，直接算除法会报 TypeError；"
                         "② Top250 的编号有“#1”和“No.1”两种写法，只匹配后者会全军覆没。",
                         14, TEXT, False)], "line_spacing": 1.35}])
    page_no(s, 7)
    return s


def s08_dashboard(prs):
    s = new_slide(prs)
    header(s, "STEP 3 · 可视化", "可视化大屏（ECharts + HTML/CSS/JS）")
    add_image_fit(s, IMG["dash"], MARGIN, Inches(1.5), CW, Inches(4.6), border=True)
    add_text(s, MARGIN, Inches(6.28), CW, Inches(0.9),
             [{"runs": [("双击 web/index.html 即可演示：", 14, CYAN, True),
                        ("ECharts 与地图数据全部本地化，离线、免安装、不需要服务器。"
                         "配色集中在 CSS 的 :root 变量里，每张图是一个独立函数，方便自己改 UI。",
                         14, MUTED, False)], "line_spacing": 1.35}])
    page_no(s, 8)
    return s


def s09_findings(prs):
    s = new_slide(prs)
    header(s, "STEP 3 · 可视化", "大屏上读出来的三个发现（和一个假信号）")
    gap = Inches(0.28)
    w = (CW - gap * 2) / 3
    finds = [
        ("发现 1", "剧情一骑绝尘", "591 部作品带“剧情”标签，是第二名的 2.2 倍；\n"
                                 "1980 年代是年代高峰（219 部）。", CYAN),
        ("发现 2", "高分 ≠ 高热度", "评分与评价人数总体正相关，但\n"
                                  "9 分以上不足 10 万人评价的有 346 部，占全库三分之一。", GOLD),
        ("发现 3", "大家在“描述作品”", "词云高频词是 剧情 / 故事 / 喜欢 / 演员 /\n"
                                    "镜头 / 感动 / 结局 —— 这埋下了建模的伏笔。", PINK),
    ]
    for i, (tag, title, body, c) in enumerate(finds):
        l = MARGIN + i * (w + gap)
        rect(s, l, Inches(1.8), w, Inches(2.35), fill=CARD)
        rect(s, l, Inches(1.8), w, Inches(0.05), fill=c)
        add_text(s, l + Inches(0.28), Inches(2.02), w - Inches(0.5), Inches(0.3),
                 [{"t": tag, "size": 12.5, "color": c, "bold": True}])
        add_text(s, l + Inches(0.28), Inches(2.34), w - Inches(0.5), Inches(0.4),
                 [{"t": title, "size": 17, "color": WHITE, "bold": True}])
        add_text(s, l + Inches(0.28), Inches(2.88), w - Inches(0.5), Inches(1.1),
                 [{"t": body, "size": 12.5, "color": MUTED, "line_spacing": 1.3}])

    rect(s, MARGIN, Inches(4.4), CW, Inches(1.75), fill=RGBColor(0x2A, 0x1E, 0x2E))
    rect(s, MARGIN, Inches(4.4), Inches(0.05), Inches(1.75), fill=PINK)
    add_text(s, MARGIN + Inches(0.35), Inches(4.6), CW - Inches(0.7), Inches(1.4),
             [{"runs": [("一个“假信号”（值得单独讲）：", 15, PINK, True),
                        ("大屏上 1990s / 2000s 的平均分只有 ", 15, TEXT, False),
                        ("2.72 / 5.13", 15, GOLD, True),
                        ("，看起来像“那个年代片子差”。查下去才发现：这两个年代分别只有 ", 15, TEXT, False),
                        ("11/38、21/38", 15, GOLD, True),
                        (" 部抓到了评分分布，全库缺评分的 110 部里有 44 部挤在这两个只占作品总数 7% 的年代里。",
                         15, TEXT, False)], "line_spacing": 1.4, "space_after": 8},
              {"runs": [("教训：", 14, CYAN, True),
                        ("大屏上的每一张图，都要先问一句“它的分母是谁”。", 14, TEXT, False)]}])
    page_no(s, 9)
    return s


def s10_task(prs):
    s = new_slide(prs)
    header(s, "STEP 4 · 文本建模", "问题怎么定的：标签与评估")
    half = (CW - Inches(0.3)) / 2

    rect(s, MARGIN, Inches(1.8), half, Inches(2.7), fill=CARD)
    rect(s, MARGIN, Inches(1.8), half, Inches(0.05), fill=PINK)
    add_text(s, MARGIN + Inches(0.3), Inches(2.02), half - Inches(0.6), Inches(0.4),
             [{"t": "先排除了一个不能用的标签", "size": 16, "color": PINK, "bold": True}])
    bullets(s, MARGIN + Inches(0.3), Inches(2.56), half - Inches(0.6), Inches(1.9), [
        "想用“≥3 星 = 喜欢”：正负比 98.4% : 1.6%（4539 : 75）",
        "→ 全猜“喜欢”就有 98.4% 准确率，任何指标都失去意义",
        "改用“5 星 vs ≤4 星”：57.5% : 42.5%（2651 : 1963）",
        "→ 接近平衡，macro-F1 与 AUC 才有解释力",
    ], size=12.5, gap=7, mark_color=PINK)

    l2 = MARGIN + half + Inches(0.3)
    rect(s, l2, Inches(1.8), half, Inches(2.7), fill=CARD)
    rect(s, l2, Inches(1.8), half, Inches(0.05), fill=CYAN)
    add_text(s, l2 + Inches(0.3), Inches(2.02), half - Inches(0.6), Inches(0.4),
             [{"t": "评估三件套（自我约束）", "size": 16, "color": CYAN, "bold": True}])
    bullets(s, l2 + Inches(0.3), Inches(2.56), half - Inches(0.6), Inches(1.9), [
        "5 折分层交叉验证，指标全部 out-of-fold",
        "~每条样本都被“没见过它”的模型预测过一次",
        "同时报 AUC：不被类别比例和阈值绑架",
        "每个任务都写明多数类基线，不许拿 60% 邀功",
    ], size=12.5, gap=7)

    rect(s, MARGIN, Inches(4.75), CW, Inches(1.6), fill=CARD)
    rect(s, MARGIN, Inches(4.75), Inches(0.05), Inches(1.6), fill=GOLD)
    add_text(s, MARGIN + Inches(0.35), Inches(4.95), CW - Inches(0.7), Inches(1.25),
             [{"runs": [("主任务：", 15, GOLD, True),
                        ("只看一条短评的文字，判断它是 5 星（力荐）还是 ≤4 星。可用样本 ", 15, TEXT, False),
                        ("4612 条", 15, CYAN, True),
                        ("（4695 条去掉 81 条没打星的、2 条正文为空的）。", 15, TEXT, False)],
               "line_spacing": 1.35, "space_after": 8},
              {"runs": [("副任务：", 15, GOLD, True),
                        ("① 差评 / 中评 / 好评 三分类；② 短评 → 电影题材分类；③ 换不同“好评分界线”做诊断。",
                         15, TEXT, False)], "line_spacing": 1.35}])
    page_no(s, 10)
    return s


def s11_models(prs):
    s = new_slide(prs)
    header(s, "STEP 4 · 文本建模", "七种模型横向对比：都很弱，而且弱得很一致")
    data = [
        ["模型", "准确率", "macro-F1", "AUC"],
        ["TF-IDF 词(1,2) + 线性 SVM", "0.5752", "0.5655", "0.6009"],
        ["TF-IDF 词(1,2) + 逻辑回归", "0.5880", "0.5803", "0.6212"],
        ["词频(1,2) + 朴素贝叶斯", "0.5987", "0.5800", "0.6224"],
        ["TF-IDF 字(2,3) + 线性 SVM", "0.5939", "0.5829", "0.6237"],
        ["TF-IDF 字(2,3) + 逻辑回归", "0.6060", "0.5990", "0.6465"],
        ["词 + 字拼接 + 线性 SVM", "0.5930", "0.5818", "0.6223"],
        ["词 + 字拼接 + 逻辑回归", "0.6067", "0.5991", "0.6449"],
        ["—— 多数类基线（全猜 5 星）——", "0.5748", "—", "0.5000"],
    ]
    add_table(s, MARGIN, Inches(1.8), CW, data, [4.6, 1.6, 1.6, 1.6],
              row_h=0.365, head_h=0.42, size=13, highlight_rows=(5, 7))

    items = [
        "字级 n-gram 比词袋好（AUC 0.647 vs 0.621）：中文短评口语化、新词多，jieba 切不准反而丢信息",
        "词 + 字拼接并没有更好：两者提供的其实是同一份信息，堆在一起只是增加维度",
        "所有模型都在 0.57~0.61 之间爬 → 不是参数没调好，而是信息量本身就到顶了",
    ]
    bullets(s, MARGIN, Inches(5.42), CW, Inches(1.6), items, size=14, gap=9)
    page_no(s, 11)
    return s


def s12_boundary(prs):
    s = new_slide(prs)
    header(s, "STEP 4 · 关键实验", "换个分界线，模型的预测力就变了")
    add_image_fit(s, IMG["fig1"], MARGIN, Inches(1.72), Inches(8.0), Inches(4.3))
    l = MARGIN + Inches(8.25)
    w = CW - Inches(7.75)
    rows = [
        ("5星 vs 1-2星", "AUC 0.700"),
        ("5星 vs 3星", "AUC 0.718"),
        ("5星 vs 4星（相邻档）", "AUC 0.623"),
        ("3星 vs 1-2星", "AUC 0.515 ≈ 瞎猜"),
    ]
    y = Inches(1.75)
    for i, (k, v) in enumerate(rows):
        rect(s, l, y, w, Inches(0.62), fill=CARD)
        rect(s, l, y, Inches(0.04), Inches(0.62), fill=[CYAN, CYAN, PINK, PINK][i])
        add_text(s, l + Inches(0.22), y + Inches(0.11), w - Inches(0.4), Inches(0.4),
                 [{"runs": [(k + "　", 13, TEXT, True), (v, 12.5, CYAN if i < 2 else PINK, True)]}])
        y += Inches(0.72)

    rect(s, l, y + Inches(0.06), w, Inches(1.9), fill=RGBColor(0x2A, 0x1E, 0x2E))
    add_text(s, l + Inches(0.22), y + Inches(0.26), w - Inches(0.44), Inches(1.6),
             [{"runs": [("AUC 随“态度差距”单调上升。", 13.5, PINK, True)], "space_after": 6},
              {"runs": [("隔着两档比有 0.718，挨着比掉到 0.623，"
                         "而 3星 vs 1-2星 只有 0.515。", 12.5, TEXT, False)],
               "line_spacing": 1.3, "space_after": 6},
              {"runs": [("结论：不是模型没用，是“4 星和 5 星”在文本上本来就分不开 —— "
                         "这是标注本身的主观性。", 12.5, CYAN, False)], "line_spacing": 1.3}])
    page_no(s, 12)
    return s


def s13_features(prs):
    s = new_slide(prs)
    header(s, "STEP 4 · 模型学到了什么", "差评靠的是句式，不是脏话")
    add_image_fit(s, IMG["fig3"], MARGIN, Inches(1.6), Inches(8.0), Inches(4.35))
    l = MARGIN + Inches(8.25)
    w = CW - Inches(8.25)

    rect(s, l, Inches(1.68), w, Inches(2.0), fill=CARD)
    rect(s, l, Inches(1.68), w, Inches(0.05), fill=PINK)
    add_text(s, l + Inches(0.2), Inches(1.88), w - Inches(0.4), Inches(1.7),
             [{"t": "最像「≤4 星」的特征", "size": 13.5, "color": PINK, "bold": True,
               "space_after": 6},
              {"t": "女主 · 了， · 无聊 · 这剧 · 观众 · ，但 · 人物 · 套路 · 故事 · 有点 · 其实 · 还是",
               "size": 12, "color": TEXT, "line_spacing": 1.3}])

    rect(s, l, Inches(3.82), w, Inches(2.13), fill=RGBColor(0x2A, 0x1E, 0x2E))
    add_text(s, l + Inches(0.2), Inches(4.0), w - Inches(0.4), Inches(1.85),
             [{"t": "中文影评的差评是“欲扬先抑”", "size": 13, "color": GOLD, "bold": True,
               "space_after": 6},
              {"t": "权重最高的不是“难看/垃圾”，而是“，但 / 其实 / 有点 / 还是”这类转折连词 —— "
                    "先夸两句，再“但是……”。", "size": 11.5, "color": TEXT, "line_spacing": 1.3,
               "space_after": 6},
              {"t": "模型抓到的其实是句式结构，而不是情感词。于是“其实还不错，但结局差点意思”"
                    "和“其实很棒”字面距离极近。", "size": 11.5, "color": MUTED, "line_spacing": 1.3}])
    page_no(s, 13)
    return s


def s14_baseline(prs):
    s = new_slide(prs)
    header(s, "STEP 4 · 两个对照", "不看文本的基线，把文本模型比下去了")
    data = [
        ["参照", "准确率", "说明"],
        ["恒猜 5 星", "0.5748", "绝对下限"],
        ["只看“这是哪部电影”（id one-hot + 逻辑回归）", "0.5768", "几乎等于没看"],
        ["同片其他短评的多数票（严格留一）", "0.6123", "完全不读文本，只数同片别人打了几星"],
        ["文本模型（主任务）", "0.6060", "没能跑赢上面那个规则"],
    ]
    add_table(s, MARGIN, Inches(1.75), Inches(7.1), data, [4.2, 1.3, 3.4],
              row_h=0.46, head_h=0.44, size=12.5, highlight_rows=(3,))

    add_text(s, MARGIN, Inches(4.3), Inches(7.1), Inches(1.6),
             [{"runs": [("必须诚实说：", 14, PINK, True),
                        ("文本模型没有跑赢一个完全不读文本的规则。", 14, TEXT, False)],
               "space_after": 6, "line_spacing": 1.35},
              {"t": "但那个规则需要“同片已有若干条短评”，而我们的数据每部平均只有 4.9 条"
                    "（939 部里 118 部全是 5 星、39 部一条 5 星都没有），它利用的其实是"
                    "“这批高分电影口碑都不错”这个先验。它的意义是告诉我们：短评文本没有提供额外的判别信息。",
               "size": 12.5, "color": MUTED, "line_spacing": 1.3}])

    add_text(s, Inches(8.35), Inches(1.72), CW - Inches(7.5), Inches(0.35),
             [{"t": "副任务：短评 → 电影题材", "size": 15, "color": CYAN, "bold": True}])
    add_image_fit(s, IMG["fig5"], Inches(8.35), Inches(2.1), CW - Inches(7.5), Inches(2.85))
    add_text(s, Inches(8.35), Inches(5.15), CW - Inches(7.5), Inches(1.2),
             [{"runs": [("动画 vs 剧情：准确率 78.5%、AUC 0.805（+28.5pp）", 13, GOLD, True)],
               "space_after": 6, "line_spacing": 1.3},
              {"t": "同一批文本、同一个模型：判题材（+0.285）远好于判态度（+0.031）。",
               "size": 12.5, "color": TEXT, "line_spacing": 1.3}])
    page_no(s, 14)
    return s


def s15_conclusion(prs):
    s = new_slide(prs)
    header(s, "CONCLUSION", "结论与反思")
    gap = Inches(0.28)
    w = (CW - gap * 2) / 3
    concl = [
        ("①", "这是一个弱信号任务", "最好的模型 AUC 0.647、准确率 60.6%，"
                                  "只比多数类基线高 3.1pp，且打不过“同片多数票”。", CYAN),
        ("②", "弱的原因在数据，不在模型", "相邻星级在文本上几乎无差别；"
                                       "差评被礼貌转折句式包裹；好评:差评 = 55:1。", GOLD),
        ("③", "文本更擅长判题材", "判题材 +28.5pp，判态度 +3.1pp —— "
                                "人们写影评时主要在描述作品，而不是表达打分。", PINK),
    ]
    for i, (no, title, body, c) in enumerate(concl):
        l = MARGIN + i * (w + gap)
        rect(s, l, Inches(1.75), w, Inches(2.3), fill=CARD)
        rect(s, l, Inches(1.75), w, Inches(0.05), fill=c)
        add_text(s, l + Inches(0.28), Inches(1.95), w - Inches(0.5), Inches(0.5),
                 [{"t": no, "size": 24, "color": c, "bold": True}])
        add_text(s, l + Inches(0.28), Inches(2.42), w - Inches(0.5), Inches(0.4),
                 [{"t": title, "size": 16, "color": WHITE, "bold": True}])
        add_text(s, l + Inches(0.28), Inches(2.92), w - Inches(0.5), Inches(1.0),
                 [{"t": body, "size": 12.5, "color": MUTED, "line_spacing": 1.3}])

    rect(s, MARGIN, Inches(4.28), CW, Inches(1.1), fill=CARD)
    rect(s, MARGIN, Inches(4.28), Inches(0.05), Inches(1.1), fill=CYAN)
    add_text(s, MARGIN + Inches(0.35), Inches(4.46), CW - Inches(0.7), Inches(0.8),
             [{"runs": [("这个项目的价值：", 15, CYAN, True),
                        ("不是“做出了一个 97% 的情感分析器”，而是把问题问清楚了 —— "
                         "一个看起来很自然的任务，到底能不能做、天花板在哪、为什么。", 15, TEXT, False)],
               "line_spacing": 1.35}])

    add_text(s, MARGIN, Inches(5.62), CW, Inches(1.2),
             [{"runs": [("继续做的方向：", 14.5, GOLD, True),
                        ("换任务比换模型有用（题材分类、是否剧透、是否提到导演）；"
                         "补采差评把 55:1 的样本做均衡；不要用星级当“喜欢”，"
                         "改用同一部电影内部的相对评分。", 14.5, TEXT, False)],
               "line_spacing": 1.35}])
    page_no(s, 15)
    return s


def s16_thanks(prs):
    s = new_slide(prs)
    rect(s, Inches(0), Inches(0), SW, Inches(0.10), fill=CYAN)
    add_text(s, MARGIN, Inches(2.15), CW, Inches(1.0),
             [{"t": "谢谢，请老师和同学批评指正", "size": 40, "color": WHITE, "bold": True,
               "align": PP_ALIGN.CENTER}])
    add_text(s, MARGIN, Inches(3.35), CW, Inches(0.5),
             [{"t": "Q & A", "size": 18, "color": CYAN, "bold": True, "align": PP_ALIGN.CENTER}])

    rect(s, Inches(3.4), Inches(4.15), Inches(6.5), Inches(1.75), fill=CARD)
    add_text(s, Inches(3.7), Inches(4.35), Inches(5.9), Inches(1.4),
             [{"t": "现场可演示的三件交付物", "size": 14, "color": GOLD, "bold": True,
               "align": PP_ALIGN.CENTER, "space_after": 8},
              {"t": "web/index.html　—　可视化大屏（离线双击即可）", "size": 12.5,
               "color": TEXT, "align": PP_ALIGN.CENTER, "space_after": 4},
              {"t": "export/douban_movies.xlsx　—　1052 部作品 + 4695 条短评", "size": 12.5,
               "color": TEXT, "align": PP_ALIGN.CENTER, "space_after": 4},
              {"t": "analysis/报告.md　+　建模报告.md　—　完整图文报告", "size": 12.5,
               "color": TEXT, "align": PP_ALIGN.CENTER}])
    return s


# ---------------------------------------------------------------- 主流程
def main():
    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH
    for fn in (s01_cover, s02_overview, s03_stages, s04_collect_scale, s05_collect_method,
               s06_quality, s07_clean, s08_dashboard, s09_findings, s10_task,
               s11_models, s12_boundary, s13_features, s14_baseline, s15_conclusion,
               s16_thanks):
        fn(prs)
    prs.save(OUT)
    print("已生成：", OUT)
    print("页数：", len(prs.slides))


if __name__ == "__main__":
    main()
