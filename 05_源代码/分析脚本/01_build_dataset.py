# -*- coding: utf-8 -*-
"""第 1 步：从 douban.db 生成两张“分析就绪”的表（只用标准库，不依赖 pandas）。

输出（都在 analysis/ 目录下）：
  analysis_movies.csv    每部作品一行 + 派生特征（类型拆列、片长转数字、口碑形态指标…）
  analysis_comments.csv  每条热门短评一行 + 清洗后正文与两个标签

对应样板项目的 Filting.ipynb（数据清洗与特征工程），但更克制：
不编造字段，缺失就留空，并在日志里把缺失数量打出来。
"""
import csv
import math
import re
import sqlite3
import statistics
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
DB = BASE / "data" / "douban.db"
OUT_MOVIES = HERE / "analysis_movies.csv"
OUT_COMMENTS = HERE / "analysis_comments.csv"

# ---------------------------------------------------------------- 清洗工具
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_AT = re.compile(r"@[\w\-\u4e00-\u9fff]+")
RE_TOPIC = re.compile(r"#([^#]{1,20})#")
RE_KEEP = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")
RE_DURATION = re.compile(r"(\d+)\s*分钟")
RE_YEAR = re.compile(r"(19|20)\d{2}")
# 榜单排名：电脑端页面写成 `豆瓣电影Top250#1` / `悬疑类欧洲剧榜#3`，
# 早期手机端接口写的是 `豆瓣电影Top250 No.1`，两种都要认
RE_HONOR_NO = re.compile(r"(?:#|\bNo\.)\s*(\d+)")


def clean_text(s):
    """短评正文清洗：去链接/at/话题标签，只留中文、字母、数字。"""
    if not s:
        return ""
    s = RE_URL.sub(" ", s)
    s = RE_AT.sub(" ", s)
    s = RE_TOPIC.sub(r"\1", s)
    s = RE_KEEP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def to_int(s, pat):
    if not s:
        return None
    m = pat.search(s)
    return int(m.group(1)) if m else None


def split_multi(s):
    if not s:
        return []
    return [x.strip() for x in s.split("/") if x.strip()]


def first_year(s):
    if not s:
        return None
    m = RE_YEAR.search(s)
    return int(m.group(0)) if m else None


def fnum(x):
    return "" if x is None else x


def has_emoji(s):
    for ch in s or "":
        o = ord(ch)
        if 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF:
            return 1
    return 0


def to_i(x):
    """SQLite 里数字列可能是字符串，统一转 int（失败返回 None）。"""
    if x is None or x == "":
        return None
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def to_f(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 读库
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
movies = conn.execute(
    "SELECT * FROM movies WHERE detail_done=1 ORDER BY id").fetchall()
comments = conn.execute(
    "SELECT * FROM comments ORDER BY movie_id, comment_id").fetchall()

# 每部作品的短评聚合（条数、平均星级、平均有用数、正文平均字数）
agg = {}
by_movie = {}
for c in comments:
    by_movie.setdefault(c["movie_id"], []).append(c)
for mid, rows in by_movie.items():
    stars = [r["rating"] for r in rows if r["rating"] is not None]
    votes = [r["votes"] for r in rows if r["votes"] is not None]
    lens = [len(clean_text(r["content"])) for r in rows]
    agg[mid] = {
        "n_comments": len(rows),
        "avg_cstar": round(sum(stars) / len(stars), 3) if stars else "",
        "std_cstar": round(statistics.pstdev(stars), 3) if len(stars) > 1 else "",
        "avg_cvotes": round(sum(votes) / len(votes), 1) if votes else "",
        "avg_clen": round(sum(lens) / len(lens), 1) if lens else "",
    }

# ---------------------------------------------------------------- 作品表
# 类型是「多值」字段：先数一遍全库类型词频，取 Top15 做成 one-hot 指示列
# （样板项目 Filting.ipynb 里手工写的 genre_喜剧 / genre_犯罪 就是这个思路的雏形）
from collections import Counter  # noqa: E402

genre_counter = Counter()
for m in movies:
    for g in split_multi(m["genres"]):
        genre_counter[g] += 1
TOP_GENRES = [g for g, _ in genre_counter.most_common(15)]

MOVIE_COLS = [
    "id", "title", "year", "decade", "subtype", "is_movie",
    "n_genres", "genres", "genres_raw", "country_main", "n_countries", "countries",
    "languages", "duration_min", "release_year", "pubdate",
    "rating_num", "rating_band", "votes", "log_votes", "votes_band",
    "p5", "p4", "p3", "p2", "p1", "good_rate", "bad_rate", "polarization",
    "comment_count", "review_count", "talk_ratio", "imdb",
    "honor", "is_top250", "honor_no", "has_rating",
    "intro_len", "director_n", "actor_n",
    "n_comments", "avg_cstar", "std_cstar", "avg_cvotes", "avg_clen",
] + ["genre_%s" % g for g in TOP_GENRES]

n_missing_rating = 0
with open(OUT_MOVIES, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(MOVIE_COLS)
    for m in movies:
        year = to_i(m["year"])
        p5, p4, p3, p2, p1 = (to_f(m["rating_p5"]), to_f(m["rating_p4"]), to_f(m["rating_p3"]),
                              to_f(m["rating_p2"]), to_f(m["rating_p1"]))
        has_rating = p5 is not None
        if not has_rating:
            n_missing_rating += 1
        if has_rating:
            good = round((p5 or 0) + (p4 or 0), 2)
            bad = round((p2 or 0) + (p1 or 0), 2)
            polar = round((p5 or 0) - (p1 or 0), 2)
        else:
            good = bad = polar = ""
        genres = split_multi(m["genres"])
        countries = split_multi(m["countries"])
        a = agg.get(m["id"], {})
        votes = to_i(m["votes"])
        rating_num = to_f(m["rating_num"])
        cc = to_i(m["comment_count"])
        row = [
            m["id"], m["title"], fnum(year),
            ("%ds" % ((year // 10) * 10)) if year else "",
            m["subtype"] or "", 1 if (m["subtype"] or "") == "movie" else 0,
            len(genres), "|".join(genres), m["genres"] or "",
            countries[0] if countries else "", len(countries), m["countries"] or "",
            m["languages"] or "", fnum(to_int(m["durations"], RE_DURATION)),
            fnum(first_year(m["pubdate"])), m["pubdate"] or "",
            fnum(rating_num),
            ("%d分档" % int(rating_num)) if rating_num is not None else "",
            fnum(votes),
            round(math.log10(votes), 3) if votes else "",
            (["10 以下", "10-100", "100-1000", "1000-1万", "1万-10万", "10万-100万",
              "100万以上"][min(6, int(math.log10(votes)))]) if votes else "",
            fnum(p5), fnum(p4), fnum(p3), fnum(p2), fnum(p1), good, bad, polar,
            fnum(cc), fnum(m["review_count"]),
            round(1.0 * cc / votes, 4) if (cc and votes) else "",
            m["imdb"] or "",
            m["honor"] or "",
            1 if "Top250" in (m["honor"] or "") else 0,
            fnum(to_int(m["honor"], RE_HONOR_NO)),
            1 if has_rating else 0,
            len(m["intro"] or ""),
            len(split_multi(m["directors"])), len(split_multi(m["actors"])),
            a.get("n_comments", 0), a.get("avg_cstar", ""), a.get("std_cstar", ""),
            a.get("avg_cvotes", ""), a.get("avg_clen", ""),
        ] + [1 if g in genres else 0 for g in TOP_GENRES]
        w.writerow(row)

# ---------------------------------------------------------------- 短评表
COM_COLS = [
    "comment_id", "movie_id", "movie_title", "year", "subtype", "genres",
    "rating", "label_top", "label_pos",
    "content", "content_clean", "n_chars", "n_excl", "n_ques", "n_ellipsis",
    "has_emoji", "is_short",
    "create_time", "create_year", "create_month",
    "ip_location", "has_ip", "user_id", "user_name", "votes", "log_votes",
]
idx = {m["id"]: m for m in movies}
n_no_star = 0
with open(OUT_COMMENTS, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(COM_COLS)
    for c in comments:
        m = idx.get(c["movie_id"])
        rating = to_f(c["rating"])
        if rating is None:
            n_no_star += 1
        ct = c["create_time"] or ""
        raw = c["content"] or ""
        cl = clean_text(raw)
        votes = to_i(c["votes"]) or 0
        w.writerow([
            c["comment_id"], c["movie_id"], m["title"] if m else "",
            fnum(m["year"]) if m else "", (m["subtype"] or "") if m else "",
            (m["genres"] or "") if m else "",
            fnum(rating),
            (1 if rating == 5 else 0) if rating is not None else "",
            (1 if rating >= 3 else 0) if rating is not None else "",
            raw, cl, len(cl),
            raw.count("！") + raw.count("!"), raw.count("？") + raw.count("?"),
            raw.count("……") + raw.count("..."),
            has_emoji(raw), 1 if len(cl) < 10 else 0,
            ct, ct[:4], ct[5:7],
            c["ip_location"] or "", 1 if (c["ip_location"] or "") else 0,
            c["user_id"] or "", c["user_name"] or "", votes,
            round(math.log10(votes + 1), 3),
        ])

conn.close()

# ---------------------------------------------------------------- 日志
print("已写出：")
print("  %s（%d 行）" % (OUT_MOVIES.name, len(movies)))
print("  %s（%d 行）" % (OUT_COMMENTS.name, len(comments)))
print()
print("派生过程中的缺失情况（这些在 CSV 里是空单元格，不是 0）：")
print("  没有评分分布的作品            %d / %d" % (n_missing_rating, len(movies)))
print("  没有星级的短评                %d / %d" % (n_no_star, len(comments)))
print("  片长解析不出来（非“N分钟”）  %d 部" % sum(
    1 for m in movies if to_int(m["durations"], RE_DURATION) is None))
print("  拿不到上映年份（pubdate 缺失）%d 部" % sum(
    1 for m in movies if first_year(m["pubdate"]) is None))
print()
print("标签分布（建模要用）：")
rows = [c for c in comments if c["rating"] is not None]
top = sum(1 for c in rows if c["rating"] == 5)
pos = sum(1 for c in rows if c["rating"] >= 3)
print("  力荐(5星) / 非力荐(<=4星)  = %d / %d  (%.1f%% / %.1f%%)"
      % (top, len(rows) - top, 100.0 * top / len(rows), 100.0 * (len(rows) - top) / len(rows)))
print("  喜欢(>=3星) / 不喜欢(<=2星) = %d / %d  (%.1f%% / %.1f%%)  ← 样板项目用的就是这个标签"
      % (pos, len(rows) - pos, 100.0 * pos / len(rows), 100.0 * (len(rows) - pos) / len(rows)))
