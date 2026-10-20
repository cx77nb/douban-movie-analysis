# -*- coding: utf-8 -*-
"""
02_export_web_data.py —— 把「分析表」变成大屏能直接吃的 JS 数据文件

这个脚本只做一件事：
    读  analysis/analysis_movies.csv + analysis_comments.csv
    写  web/js/data.js        （window.DASH_DATA = {...}，大屏所有图表的数据源）
        web/js/china-map.js   （window.CHINA_GEOJSON = {...}，中国地图轮廓）

为什么写成 .js 而不是 .json？
    双击打开 index.html 时地址是 file://，浏览器禁止网页 fetch 本地 json（跨域限制）。
    而 <script src="data.js"> 没有这个限制，所以把数据包成一句 JS 赋值最省事，
    不用起服务器、不用装任何东西，双击就能看。

用法（在项目根目录）：
    .venv\\Scripts\\python.exe analysis\\02_export_web_data.py
"""

import csv
import io
import json
import math
import os
import re
import sys
from collections import Counter

# ---------- 0. 路径：全部相对于项目根目录 ----------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_MOVIES = os.path.join(BASE, "analysis", "analysis_movies.csv")
SRC_COMMENTS = os.path.join(BASE, "analysis", "analysis_comments.csv")
GEO_IN = os.path.join(BASE, "analysis", "geo", "china_raw.json")
OUT_DATA = os.path.join(BASE, "web", "js", "data.js")
OUT_MAP = os.path.join(BASE, "web", "js", "china-map.js")


# ---------- 1. 小工具 ----------
def read_csv(path):
    """读 csv，返回 list[dict]（表头当 key）。"""
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(v, default=0.0):
    """把 csv 里的字符串转成数字，转不动就给默认值。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def split_multi(text):
    """'剧情|悬疑'  /  '美国 / 英国'  →  ['剧情', '悬疑']。"""
    return [x.strip() for x in re.split(r"[|/]", text or "") if x.strip()]


# ---------- 2. 读数据 ----------
movies = read_csv(SRC_MOVIES)
comments = read_csv(SRC_COMMENTS)
print("读入：作品 %d 行，短评 %d 行" % (len(movies), len(comments)))


# ---------- 3. KPI 卡片 ----------
rated = [m for m in movies if m.get("has_rating") == "1"]
avg_rating = sum(num(m["rating_num"]) for m in rated) / max(len(rated), 1)
top250 = [m for m in movies if m.get("is_top250") == "1"]
kpi = {
    "works": len(movies),                                  # 作品总数
    "movies": sum(1 for m in movies if m.get("subtype") == "movie"),
    "tvs": sum(1 for m in movies if m.get("subtype") == "tv"),
    "rated": len(rated),                                   # 有评分分布的作品
    "comments": len(comments),                             # 短评条数
    "top250": len(top250),                                 # 豆瓣 Top250 上榜
    "avg_rating": round(avg_rating, 2),                    # 平均分
    "comment_movies": len({c["movie_id"] for c in comments}),
}


# ---------- 4. 类型 Top10（横向柱状图） ----------
genre_counter = Counter()
for m in movies:
    for g in split_multi(m.get("genres")):
        genre_counter[g] += 1
genre_top = [{"name": g, "value": n} for g, n in genre_counter.most_common(10)]


# ---------- 5. 年代分布（柱状 + 折线双轴） ----------
decade_sum, decade_cnt = Counter(), Counter()
for m in movies:
    d = (m.get("decade") or "").strip()
    if not d:
        continue
    decade_cnt[d] += 1
    if m.get("has_rating") == "1":
        decade_sum[d] += num(m["rating_num"])
decade_labels = sorted(decade_cnt.keys())                  # 1950s ... 2020s
decade = {
    "labels": decade_labels,
    "counts": [decade_cnt[d] for d in decade_labels],
    "avg": [round(decade_sum[d] / decade_cnt[d], 2) if decade_cnt[d] else 0 for d in decade_labels],
}


# ---------- 6. 短评星级分布（环形图） ----------
star_cnt = Counter()
for c in comments:
    r = (c.get("rating") or "").strip()
    star_cnt[int(float(r)) if r else 0] += 1
star_dist = [{"name": ("%d星" % k) if k else "未评分", "value": star_cnt.get(k, 0)}
             for k in (5, 4, 3, 2, 1, 0)]


# ---------- 7. 制片国家/地区 Top10 ----------
country_counter = Counter()
for m in movies:
    for c in split_multi(m.get("countries")):
        country_counter[c] += 1
country_top = [{"name": c, "value": n} for c, n in country_counter.most_common(10)]


# ---------- 8. 中国地图：短评 IP 归属地 ----------
# 豆瓣给的是省名简写（"北京"/"广东"/"内蒙古"），地图里是全称（"北京市"/"内蒙古自治区"），
# 所以先把地图里的全称压成简写，做一张对照表。
with io.open(GEO_IN, encoding="utf-8") as fh:
    geo = json.load(fh)


def short_name(full):
    """'内蒙古自治区' → '内蒙古'；'广西壮族自治区' → '广西'。"""
    for suf in ("特别行政区", "自治区", "省", "市"):
        if full.endswith(suf):
            full = full[: -len(suf)]
            break
    for pre in ("壮族", "回族", "维吾尔"):
        full = full.replace(pre, "")
    return full


name_map = {short_name(f["properties"]["name"]): f["properties"]["name"]
            for f in geo["features"] if f["properties"]["name"]}

ip_counter = Counter()
overseas = 0
for c in comments:
    ip = (c.get("ip_location") or "").strip()
    if not ip:
        continue
    if ip in name_map:                                     # 国内省份
        ip_counter[name_map[ip]] += 1
    else:                                                  # 美国/日本…算海外
        overseas += 1
map_data = [{"name": k, "value": v} for k, v in ip_counter.items()]
map_max = max([d["value"] for d in map_data] or [1])


# ---------- 9. 评分 vs 评价人数（散点图） ----------
scatter = [[round(num(m["rating_num"]), 1), int(num(m["votes"])), m["title"]]
           for m in rated if num(m["votes"]) > 0]


# ---------- 10. 高分榜 Top10 ----------
def top_key(m):
    return (num(m["rating_num"]), num(m["votes"]))


top_movies = []
seen_title = set()
for m in sorted(rated, key=top_key, reverse=True):
    if m["title"] in seen_title:                    # 同名作品（如「是，大臣」各季）只留评价人数最多的那部
        continue
    seen_title.add(m["title"])
    top_movies.append({"name": m["title"], "rating": num(m["rating_num"]), "votes": int(num(m["votes"])),
                       "year": m.get("year") or "", "genres": (m.get("genres") or "").replace("|", " ")})
    if len(top_movies) >= 10:
        break


# ---------- 11. 短评时间趋势（按年） ----------
year_cnt = Counter()
for c in comments:
    y = (c.get("create_year") or "").strip()
    if y and y.isdigit():
        year_cnt[int(y)] += 1
years = sorted(year_cnt)
year_trend = {"labels": [str(y) for y in years], "values": [year_cnt[y] for y in years]}


# ---------- 12. 短评词云（有 jieba 用 jieba，没有就用二字词兜底） ----------
STOP = set("的了是我你他她它这那不在有和就都被把很也都会能可就而及与等一个没有自己什么"
           "这么那么还是但是因为所以如果虽然然后电影一部片子觉得真是就是不是好太非常"
           "我们你们他们可以这个那个一下已经一直但是而且以及对于关于由于".split())
# 词云里不想出现的高频口水词（用 jieba 分词时过滤掉；内容词如“演技/剧情/好看”保留）
STOP |= set("觉得 知道 看到 时候 因为 所以 最后 完全 其实 结果 东西 电影 片子 一部 真的 非常 "
            "特别 哈哈 基本 直接 而且 但是 不过 还是 就是 只是 有点 一种 一样 一直 一起 出来 "
            "竟然 居然 终于 果然 毕竟 虽然 如果 这样 那样 怎么 什么 为什么 多少 现在 当时 之后 "
            "之前 以后 以前 开始 结束 起来 下去 上去 过来 他们 她们 我们 你们 自己 别人 大家 "
            "这个 那个 一下 已经 可以 没有 一个 真是 不是 就是 东西 事情 地方".split())
# 兜底用：常见的无意义二字组合
BAD_BIGRAM = ("的", "了", "是", "我", "你", "他", "这", "那", "不", "在", "有", "和", "就", "都",
              "也", "会", "能", "可", "而", "及", "与", "等", "一", "个", "很", "太", "好")

text_all = " ".join((c.get("content_clean") or "") for c in comments)
words = []
try:
    import jieba                                                  # 装了 jieba 就用它分词
    for w in jieba.cut(text_all):
        w = w.strip()
        if len(w) >= 2 and w not in STOP and not w.isdigit() and not w.isascii():
            words.append(w)
    src = "jieba"
except Exception:                                                 # 没装 jieba 的兜底方案
    clean = re.sub(r"[^\u4e00-\u9fa5]", "", text_all)
    for i in range(len(clean) - 1):
        bg = clean[i:i + 2]
        if bg[0] in BAD_BIGRAM or bg[1] in BAD_BIGRAM:
            continue
        words.append(bg)
    src = "bigram(兜底)"
word_cloud = [{"name": w, "value": n} for w, n in Counter(words).most_common(120) if n >= 3]
print("词云来源：%s，取词 %d 个" % (src, len(word_cloud)))


# ---------- 13. 筛选数据：按「口径（全部/电影/剧集）× 年代」重新聚合 ----------
# 大屏顶部的筛选按钮（chips）就是读这里的数据。
#   · 年代分布图（图 02）只受「口径」影响 —— 用年代去筛年代分布没有意义
#   · 类型 TOP10（图 01）、制片国家（图 06）、高分榜（图 07）同时受「口径 + 年代」影响
# 所以这里出两份：byCaliber（只按口径）和 cross（口径 × 年代 的交叉）。

CALIBERS = [("all", "全部", None), ("movie", "电影", "movie"), ("tv", "剧集", "tv")]
DECADES = [("all", "不限", None), ("1980s", "1980s", "1980s"),
           ("2010s", "2010s", "2010s"), ("2020s", "2020s", "2020s")]


def calc_genre(movs):
    """这批作品里的类型 Top10。"""
    c = Counter()
    for m in movs:
        for g in split_multi(m.get("genres")):
            c[g] += 1
    return [{"name": g, "value": n} for g, n in c.most_common(10)]


def calc_country(movs):
    """这批作品里的制片国家 Top10。"""
    c = Counter()
    for m in movs:
        for x in split_multi(m.get("countries")):
            c[x] += 1
    return [{"name": x, "value": n} for x, n in c.most_common(10)]


def calc_decade(movs):
    """这批作品的年代分布（柱=数量，线=平均分）。"""
    cnt, total = Counter(), Counter()
    for m in movs:
        d = (m.get("decade") or "").strip()
        if not d:
            continue
        cnt[d] += 1
        if m.get("has_rating") == "1":
            total[d] += num(m["rating_num"])
    labels = sorted(cnt.keys())
    return {"labels": labels,
            "counts": [cnt[d] for d in labels],
            "avg": [round(total[d] / cnt[d], 2) if cnt[d] else 0 for d in labels]}


def calc_top(movs, n=10):
    """这批作品里的高分榜 Top N（同名作品只留评价人数最多的那部）。"""
    pool = [m for m in movs if m.get("has_rating") == "1"]
    out, seen = [], set()
    for m in sorted(pool, key=top_key, reverse=True):
        if m["title"] in seen:
            continue
        seen.add(m["title"])
        out.append({"name": m["title"], "rating": num(m["rating_num"]),
                    "votes": int(num(m["votes"])), "year": m.get("year") or "",
                    "genres": (m.get("genres") or "").replace("|", " ")})
        if len(out) >= n:
            break
    return out


by_caliber, cross = {}, {}
for ck, _clab, sub in CALIBERS:
    pool = movies if sub is None else [m for m in movies if m.get("subtype") == sub]
    by_caliber[ck] = {"decade": calc_decade(pool), "n": len(pool)}
    for dk, _dlab, dec in DECADES:
        cell = pool if dec is None else [m for m in pool if (m.get("decade") or "") == dec]
        cross["%s|%s" % (ck, dk)] = {
            "genreTop": calc_genre(cell),
            "countryTop": calc_country(cell),
            "topMovies": calc_top(cell),
            "n": len(cell),
        }
print("筛选数据：口径 %d 种 × 年代 %d 种 = %d 组" % (len(CALIBERS), len(DECADES), len(cross)))


# ---------- 14. 写文件 ----------
dash = {
    "updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
    "kpi": kpi,
    "genreTop": genre_top,
    "decade": decade,
    "starDist": star_dist,
    "countryTop": country_top,
    "mapData": map_data,
    "mapMax": map_max,
    "overseas": overseas,
    "scatter": scatter,
    "topMovies": top_movies,
    "yearTrend": year_trend,
    "wordCloud": word_cloud,
    "filters": {
        "calibers": [{"key": k, "label": lab} for k, lab, _s in CALIBERS],
        "decades": [{"key": k, "label": lab} for k, lab, _d in DECADES],
        "byCaliber": by_caliber,
        "cross": cross,
    },
}

os.makedirs(os.path.dirname(OUT_DATA), exist_ok=True)
with io.open(OUT_DATA, "w", encoding="utf-8") as fh:
    fh.write("// 本文件由 analysis/02_export_web_data.py 自动生成，不要手动改\n")
    fh.write("// 生成时间：%s\n" % dash["updated"])
    fh.write("window.DASH_DATA = ")
    json.dump(dash, fh, ensure_ascii=False, separators=(",", ":"))
    fh.write(";\n")

with io.open(OUT_MAP, "w", encoding="utf-8") as fh:
    fh.write("// 本文件由 analysis/02_export_web_data.py 自动生成（源：阿里 DataV 全国 GeoJSON）\n")
    fh.write("window.CHINA_GEOJSON = ")
    json.dump(geo, fh, ensure_ascii=False, separators=(",", ":"))
    fh.write(";\n")

print("已写出：")
print("  %s  (%.1f KB)" % (OUT_DATA, os.path.getsize(OUT_DATA) / 1024.0))
print("  %s  (%.1f KB)" % (OUT_MAP, os.path.getsize(OUT_MAP) / 1024.0))
print("KPI: 作品 %d（电影 %d / 剧集 %d）、有评分分布 %d、短评 %d、Top250 %d、平均分 %.2f"
      % (kpi["works"], kpi["movies"], kpi["tvs"], kpi["rated"], kpi["comments"],
         kpi["top250"], kpi["avg_rating"]))
print("地图命中省份 %d 个，海外 %d 条" % (len(map_data), overseas))
