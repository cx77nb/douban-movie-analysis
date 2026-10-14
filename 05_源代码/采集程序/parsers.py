# -*- coding: utf-8 -*-
"""
解析层：把三个来源的原始数据（rexxar JSON / 电脑端 HTML / 手机端 HTML）变成数据库字段。

想加字段就改这里，别的地方不用动。
"""
import html as html_mod
import re


def _first(pattern, text, default=None, flags=0):
    if not text:
        return default
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else default

def _all(pattern, text, flags=0):
    if not text:
        return []
    return [x.strip() for x in re.findall(pattern, text, flags)]


def _num(text):
    """'85.4%' -> 85.4 ; '3,350,055' -> 3350055 ; '' -> None"""
    if text is None:
        return None
    s = str(text).replace(",", "").replace("%", "").strip()
    if not s:
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def _join(seq, sep=" / "):
    return sep.join([str(x) for x in seq if x])


# ---------------------------------------------------------------- rexxar 电影详情
def parse_rexxar_movie(d):
    """把 rexxar /v2/movie/<id> 的 JSON 变成 movies 表的字段。"""
    rating = d.get("rating") or {}

    def names(key):
        return [x.get("name") for x in (d.get(key) or []) if isinstance(x, dict) and x.get("name")]

    honor = [(h.get("title"), h.get("rank")) for h in (d.get("honor_infos") or [])
             if isinstance(h, dict)]
    honor_txt = "; ".join("%s%s" % (t, ("#%s" % r) if r else "") for t, r in honor if t)

    return {
        "title": d.get("title"),
        "original_title": d.get("original_title"),
        "year": str(d.get("year")) if d.get("year") else None,
        "subtype": d.get("subtype") or d.get("type"),
        "card_subtitle": d.get("card_subtitle"),
        "genres": _join(d.get("genres") or []),
        "countries": _join(d.get("countries") or []),
        "languages": _join(d.get("languages") or []),
        "durations": _join(d.get("durations") or []),
        "pubdate": _join(d.get("pubdate") or []),
        "release_date": d.get("release_date"),
        "aka": _join(d.get("aka") or []),
        "intro": (d.get("intro") or "").strip() or None,
        "tags": _join([t.get("name") for t in (d.get("tags") or []) if isinstance(t, dict)]),
        "directors": _join(names("directors")),
        "actors": _join(names("actors")),
        "rating_value": _num(rating.get("value")),
        "rating_count": _num(rating.get("count")),
        "rating_star": _num(rating.get("star_count")),
        "comment_count": _num(d.get("comment_count")),
        "review_count": _num(d.get("review_count")),
        "cover_url": d.get("cover_url") or (d.get("cover") or {}).get("url"),
        "url": d.get("url") or d.get("sharing_url"),
        "honor": honor_txt or None,
        "is_tv": 1 if (d.get("is_tv") or d.get("subtype") == "tv") else 0,
    }


# ---------------------------------------------------------------- 影人（rexxar celebrities）
def parse_celebrities(d, movie_id, limit=12):
    """返回影人 dict 列表，导演优先，之后是前几位演员。
    每项：{id, role, name, character, ord, latin_name, avatar}
    （rexxar 的影人接口是唯一能拿到影人 id 的地方，电影详情里的导演/演员只有名字。）"""
    out = []
    order = 0
    for role, key in (("导演", "directors"), ("演员", "actors")):
        for p in (d.get(key) or []):
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if not pid:
                uri = p.get("uri") or ""
                pid = uri.rstrip("/").split("/")[-1] if uri else None
            if not pid:
                continue
            avatar = p.get("avatar") or {}
            out.append({
                "id": str(pid),
                "role": role,
                "name": p.get("name"),
                "character": p.get("character"),
                "ord": order,
                "latin_name": p.get("latin_name"),
                "avatar": avatar.get("large") or avatar.get("normal"),
            })
            order += 1
            if len(out) >= limit:
                return out
    return out


# ---------------------------------------------------------------- 电脑端详情页（评分分布等）
def parse_pc_subject(text):
    """电脑端 /subject/<id>/ 页面。最有价值的是五星~一星占比（rexxar 接口没有）。"""
    per = _all(r'<span class="rating_per">([^<]*)</span>', text)
    while len(per) < 5:
        per.append(None)
    fields = {
        "rating_p5": _num(per[0]),
        "rating_p4": _num(per[1]),
        "rating_p3": _num(per[2]),
        "rating_p2": _num(per[3]),
        "rating_p1": _num(per[4]),
        "rating_num": _first(r'<strong class="ll rating_num"[^>]*>([^<]*)</strong>', text),
        "votes": _num(_first(r'<span property="v:votes">([^<]*)</span>', text)),
        "imdb": _first(r'<span class="pl">IMDb:</span>\s*([^\s<]+)', text),
        "pc_runtime": _first(r'<span property="v:runtime"[^>]*>([^<]*)</span>', text),
        "pc_release": _join(_all(r'<span property="v:initialReleaseDate"[^>]*>([^<]*)</span>',
                                 text)),
        "pc_aka": _first(r'<span class="pl">又名:</span>\s*([^<]*)', text),
        "pc_languages": _first(r'<span class="pl">语言:</span>\s*([^<]*)', text),
        "pc_countries": _first(r'<span class="pl">制片国家/地区:</span>\s*([^<]*)', text),
    }
    raw = {
        "rating_per": per,
        "title": _first(r'<span property="v:itemreviewed">([^<]*)</span>', text),
        "year": _first(r'<span class="year">\((\d{4})\)</span>', text),
        "genres": _all(r'<span property="v:genre">([^<]*)</span>', text),
        "directors": _all(r'rel="v:directedBy">([^<]*)</a>', text),
        "starring": _all(r'rel="v:starring">([^<]*)</a>', text)[:12],
        "release": _all(r'<span property="v:initialReleaseDate"[^>]*>([^<]*)</span>', text),
        "runtime": _first(r'<span property="v:runtime"[^>]*>([^<]*)</span>', text),
        "imdb": fields["imdb"],
        "votes": fields["votes"],
        "summary": _first(r'<span property="v:summary"[^>]*>\s*([\s\S]{0,4000}?)</span>', text),
    }
    return fields, raw


# ---------------------------------------------------------------- 电脑端详情页：整部电影
def parse_pc_movie_detail(text):
    """电脑端 /subject/<id>/ 整页 -> movies 表字段（键名与 parse_rexxar_movie 一致）。

    为什么把它当主通路：手机 rexxar 接口按 IP 限流（HTTP 400 / code 1309，实测连发
    约 72 次就中），而电脑端页面是另一套配额，而且**一页就把"电影详情 + 五星~一星
    占比"全给了** —— 一页顶原来两个接口。解开一次哈希挑战后，同一会话的后续页面
    通常不再被挑战（实测第 2 部就没有再解）。
    唯一拿不到的是 rexxar 的 tags/genres 之外的荣誉字段，但 top250 排名能单独抠。
    """
    if not text:
        return {}
    full_title = _first(r'property="v:itemreviewed">([^<]*)</span>', text)
    title, original = full_title, None
    if full_title and " " in full_title:
        head, tail = full_title.split(" ", 1)
        if head.strip() and tail.strip():
            title, original = head.strip(), tail.strip()

    def persons(attr):
        """返回 [(影人id 或 None, 姓名), ...]。
        电脑端页面的影人链接是 https://www.douban.com/personage/<id>/（不是 celebrity）。"""
        pairs = re.findall(r'href="[^"]*?/personage/(\d+)/?"[^>]*?rel="%s">([^<]+)</a>'
                           % attr, text)
        if pairs:
            return pairs
        return [(None, n) for n in _all(r'rel="%s">([^<]+)</a>' % attr, text)]

    dirs = persons("v:directedBy")
    casts = persons("v:starring")

    tags_box = _first(r'<div class="tags-body">([\s\S]{0,900}?)</div>', text)
    tags = _all(r"<a[^>]*>([^<]{1,20})</a>", tags_box) if tags_box else []

    summary = _first(r'<span property="v:summary"[^>]*>\s*([\s\S]{0,6000}?)</span>', text)
    if summary:
        summary = html_mod.unescape(re.sub(r"<[^>]+>", "", summary))
        summary = re.sub(r"\s+", " ", summary).strip() or None

    release = _all(r'<span property="v:initialReleaseDate"[^>]*>([^<]*)</span>', text)
    is_tv = 1 if re.search(r'<span class="pl">集数:</span>', text) else 0
    runtime = (_first(r'<span property="v:runtime"[^>]*>([^<]*)</span>', text)
               or _first(r"单集片长:</span>\s*([^<]*)", text))
    votes = _num(_first(r'<span property="v:votes">([^<]*)</span>', text))
    rating = _num(_first(r'<strong class="ll rating_num"[^>]*>([^<]*)</strong>', text))
    honor_rank = _first(r'class="top250-no">No\.(\d+)<', text)
    per = _all(r'<span class="rating_per">([^<]*)</span>', text)

    return {
        "title": title,
        "original_title": original,
        "year": _first(r'<span class="year">\(([^)]*)\)</span>', text),
        "subtype": "tv" if is_tv else "movie",
        "card_subtitle": None,
        "genres": _join(_all(r'<span property="v:genre">([^<]*)</span>', text)),
        "countries": _first(r"制片国家/地区:</span>\s*([^<]*)", text),
        "languages": _first(r"语言:</span>\s*([^<]*)", text),
        "durations": runtime,
        "pubdate": _join(release),
        "release_date": _join(release) or None,
        "aka": _first(r"又名:</span>\s*([^<]*)", text),
        "intro": summary,
        "tags": _join(tags),
        "directors": _join([n for _, n in dirs]),
        "actors": _join([n for _, n in casts]),
        "rating_value": rating,
        "rating_count": votes,
        "rating_star": None,          # 不编造：电脑端页面没有"星级"这个字段
        "comment_count": _num(_first(r'subject/\d+/comments[^"]*">全部\s*([\d,]+)\s*条', text)),
        "review_count": _num(_first(r'href="reviews">全部\s*([\d,]+)\s*条', text)),
        "cover_url": _first(r'property="og:image" content="([^"]*)"', text),
        "url": (_first(r'<link rel="canonical" href="([^"]*)"', text)
                or _first(r'property="v:url" content="([^"]*)"', text)),
        "honor": ("豆瓣电影Top250 No.%s" % honor_rank) if honor_rank else None,
        "is_tv": is_tv,
        "episodes": _first(r"集数:</span>\s*([^<]*)", text),
        "director_ids": _join([i for i, _ in dirs if i]),
        "actor_ids": _join([i for i, _ in casts if i]),
    }


# ---------------------------------------------------------------- 电脑端详情页里的短评
def parse_pc_comments(text, movie_id, limit=5):
    """从电脑端详情页的"短评"模块里抠出热门短评（通常 5 条）。

    为什么顺手在这儿拿：同一个页面里已经有短评了，等于**不额外发一次请求**。
    （对照 rexxar 的 interests 接口：它按 IP 限流，而且 start 超过 100 就拿不到更多。）
    只认真正渲染出来的条目——页面里那份 handlebar 模板的 data-cid 是占位符 `id`。
    """
    if not text or limit <= 0:
        return []
    out = []
    blocks = re.split(r'<div class="comment-item"\s+data-cid="(\d+)">', text)
    # re.split 带捕获组的结果形如 [前文, cid1, 块1, cid2, 块2, ...]
    for i in range(1, len(blocks) - 1, 2):
        cid, block = blocks[i], blocks[i + 1]
        content = _first(r'<span class="short">([\s\S]*?)</span>', block)
        if content:
            content = html_mod.unescape(re.sub(r"<[^>]+>", "", content))
            content = re.sub(r"\s+", " ", content).strip() or None
        star = _first(r'class="allstar(\d)0 rating"', block)
        out.append({
            "comment_id": str(cid),
            "movie_id": str(movie_id),
            "content": content,
            "rating": float(star) if star else None,
            "create_time": _first(r'<a class="comment-time"[^>]*title="([^"]*)"', block),
            "ip_location": _first(r'<span class="comment-location">([^<]*)</span>', block),
            "user_id": _first(r'<span class="comment-info">\s*<a href="[^"]*?/people/([^/"]+)/"',
                              block),
            "user_name": _first(r'<span class="comment-info">\s*<a href="[^"]*?/people/[^"]*">'
                                r'([^<]*)</a>', block),
            "votes": _num(_first(r'<span class="votes vote-count">([^<]*)</span>', block)) or 0,
            "raw": {"source": "pc_subject", "cid": cid},
        })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- 手机端影人页
def parse_m_celebrity(text, celeb_id):
    """手机端影人页 HTML，含性别/生日/出生地/简介。"""
    title = _first(r"<title>\s*([^<]*?)\s*</title>", text)
    name = title.split("-")[0].strip() if title else None
    if name in ("豆瓣", "", None):
        name = None
    meta = _first(r'<meta name="description" content="([^"]*)"', text)
    intro = None
    if meta:
        intro = re.sub(r"^[^：:]{0,24}简介[：:]", "", meta).strip() or None
    if not intro:
        intro = _first(r'<div class="detail">\s*([\s\S]{0,4000}?)\s*</div>', text)
        if intro:
            intro = re.sub(r"<[^>]+>", "", intro).strip() or None

    def info(label, pat=r"[^<\n]{1,60}"):
        return _first(label + r"[：:]\s*(" + pat + ")", text)

    return {
        "name": name,
        "latin_name": info("更多外文名") or info("外文名"),
        "gender": info("性别", r"[^<\s,，]{1,4}"),
        "birthday": info("出生日期", r"[\d年月日\-\.]{4,20}"),
        "born_place": info("出生地", r"[^<\n]{1,40}"),
        "aka_cn": info("更多中文名"),
        "aka_en": info("更多外文名"),
        "imdb": info("imdb编号", r"[^<\n]{1,20}"),
        "avatar": (_first(r'<meta property="og:image" content="([^"]*)"', text)
                   or _first(r'<img[^>]+class="[^"]*avatar[^"]*"[^>]+src="([^"]*)"', text)),
        "intro": intro,
    }


# ---------------------------------------------------------------- 短评
def parse_interests(d, movie_id):
    """rexxar interests 接口 -> comments 表记录。"""
    out = []
    for it in (d.get("interests") or []):
        if not isinstance(it, dict):
            continue
        user = it.get("user") or {}
        rating = it.get("rating") or {}
        cid = it.get("id")
        if cid is None:
            continue
        out.append({
            "comment_id": str(cid),
            "movie_id": str(movie_id),
            "content": (it.get("comment") or "").strip() or None,
            "rating": _num(rating.get("value")),
            "create_time": it.get("create_time"),
            "ip_location": it.get("ip_location"),
            "user_id": str(user.get("id")) if user.get("id") else None,
            "user_name": user.get("name"),
            "votes": _num(it.get("vote_count") if it.get("vote_count") is not None
                          else it.get("useful_count")) or 0,
            "raw": it,
        })
    return out
