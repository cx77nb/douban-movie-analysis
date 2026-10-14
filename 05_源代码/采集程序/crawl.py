# -*- coding: utf-8 -*-
"""
豆瓣电影数据采集主程序（纯标准库，不需要 pip 安装任何东西）。

用法（在 PyCharm 里右键 Run，或在终端里执行）：

    python crawl.py discover            # 第一步：发现电影 id，攒到 config.TARGET_MOVIES 部
    python crawl.py movie --limit 50    # 第二步：抓电影资料（详情 + 评分分布，一页全拿）★主通路
    python crawl.py comments --limit 50 # 第三步：抓每部电影前几条短评
    python crawl.py all                 # 一条龙跑完上面三步（可随时 Ctrl+C，重跑自动续）
    python crawl.py stats               # 看当前进度
    python crawl.py export              # 导出 CSV / Excel 到 export/ 目录

    备用/可选阶段（都不在 all 里）：
    python crawl.py detail --limit 50   # 手机接口抓详情（会按 IP 限流，见 README 第 6 节）
    python crawl.py rating --limit 50   # 单独补评分分布（movie 阶段其实已经含了）
    python crawl.py people --limit 50   # 抓影人档案（本次不需要）
    python crawl.py retry               # 把失败计数清零，让它们下次重试

每一步都能重复执行：已经抓过的不会重抓（状态存在 data/douban.db 里）。
"""
import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime

import config
import parsers
from douban_api import Blocked, BudgetExceeded, ChallengeFailed, Fetcher
from storage import Store

log = logging.getLogger("douban")


# ---------------------------------------------------------------- 安全闸
def _guard(streak, stage, last_id):
    """连续失败太多就停下。

    这是用血换来的教训：2026-10-13 那次"详情阶段"被豆瓣按 IP 限流，
    接口对每条都返回 400，而当时的代码把它当成"正常的失败"继续跑，
    40 分钟内把 500 部电影逐条标成失败——失败是静默的，日志里连一条
    WARNING 都没有。有了这道闸，接口整体挂掉时最多错 8 条就停。
    """
    if streak >= config.MAX_CONSEC_FAIL:
        log.error("连续失败 %d 次（最后一条 id=%s），判断不是偶发问题，主动停止「%s」阶段。"
                  "已抓到的数据都在库里，等一会儿或调整 config 后重跑同一条命令即可续爬。",
                  streak, last_id, stage)
        return True
    return False


# ---------------------------------------------------------------- 日志
def setup_logging():
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = config.LOG_DIR / ("crawl_%s.log" % datetime.now().strftime("%Y%m%d"))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    log.setLevel(logging.INFO)
    log.handlers.clear()

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return path


# ================================================================ 阶段 1：发现
def build_query_plan():
    """按"先粗后细"的顺序铺查询：评分带×年份带 → 类型×评分带 → 地区×评分带 → 标签/排序。"""
    plan = []
    for band in config.RATING_BANDS:
        for year in config.YEAR_BANDS:
            plan.append(("评分%s_年份%s" % (band, year),
                         {"sort": "T", "range": band, "tags": "", "year_range": year}))
    for genre in config.GENRES:
        for band in ("9,10", "8,9", "7,8"):
            plan.append(("类型%s_评分%s" % (genre, band),
                         {"sort": "T", "range": band, "tags": "", "genres": genre}))
    for country in config.COUNTRIES:
        for band in ("9,10", "8,9"):
            plan.append(("地区%s_评分%s" % (country, band),
                         {"sort": "T", "range": band, "tags": "", "countries": country}))
    plan.append(("豆瓣高分", {"sort": "S", "range": "0,10", "tags": "豆瓣高分"}))
    for s in config.SORTS:
        plan.append(("排序%s" % s, {"sort": s, "range": "0,10", "tags": ""}))
    return plan


def stage_discover(store, fetcher, target=None, max_pages=None):
    target = target or config.TARGET_MOVIES
    max_pages = max_pages or config.MAX_PAGES_PER_QUERY
    plan = build_query_plan()
    log.info("发现阶段开始：目标 %d 部，查询计划 %d 条", target, len(plan))

    for label, params in plan:
        qkey = label
        state = store.query_state(qkey)
        if state["done"]:
            continue
        total = store.counts()["电影总数"]
        if total >= target:
            log.info("已达到目标 %d 部，发现阶段结束", target)
            break

        pages_done = state["pages_done"]
        found = state["found"]
        if pages_done == 0:
            log.info("查询 [%s] %s", label, params)
        empty_streak = 0
        while pages_done < max_pages:
            start = pages_done * 20
            items = fetcher.discover(start=start, **params)
            if not items:
                empty_streak += 1
                if empty_streak == 1 and pages_done > 0:
                    # 可能是被临时限速，等一下再确认一次
                    time.sleep(20)
                    items = fetcher.discover(start=start, **params)
                if not items:
                    log.info("  [%s] start=%d 无数据，本查询翻到底（已翻 %d 页）",
                             label, start, pages_done)
                    break
            empty_streak = 0
            new = 0
            for it in items:
                mid = it.get("id")
                if mid and store.add_discovered(mid, label):
                    new += 1
            pages_done += 1
            found += new
            if new == 0:
                # 这一页全是老面孔，说明该查询已经重复，继续翻页意义不大
                log.info("  [%s] start=%d 全是重复，停止该查询", label, start)
                store.save_query_state(qkey, label, params, pages_done, found, True)
                break
            if len(items) < 20:
                break
        store.save_query_state(qkey, label, params, pages_done, found, pages_done >= max_pages)
        log.info("  [%s] 翻 %d 页，新增 %d，累计电影 %d 部",
                 label, pages_done, found, store.counts()["电影总数"])

    c = store.counts()
    log.info("发现阶段结束：电影 %d 部（目标 %d），已用查询 %d 条",
             c["电影总数"], target, c["发现的查询数"])
    return c["电影总数"]


# ================================================================ 阶段 2：详情
def stage_detail(store, fetcher, limit=0):
    ids = store.next_movies("detail", limit or 10 ** 9)
    log.info("详情阶段：待抓 %d 部", len(ids))
    ok = fail = gone = 0
    streak = 0
    for i, mid in enumerate(ids, 1):
        d = fetcher.movie_detail(mid)
        if d is None:
            store.mark_fail(mid, "detail")
            fail += 1
            streak += 1
        elif d.get("__gone__"):
            store.mark_gone(mid)
            gone += 1
            streak = 0
        else:
            d.pop("variable_modules", None)      # 体积大且没用
            store.save_detail(mid, parsers.parse_rexxar_movie(d), d)
            ok += 1
            streak = 0
        if i % 20 == 0 or i == len(ids):
            log.info("  详情 %d/%d 成功 %d 失败 %d 失效 %d", i, len(ids), ok, fail, gone)
        if _guard(streak, "详情", mid):
            break
    log.info("详情阶段结束：成功 %d，失败 %d，失效 %d", ok, fail, gone)


# ================================================================ 阶段 2：电影资料（电脑端一页全拿）
def stage_movie(store, fetcher, limit=0):
    """一部电影只发 1 次请求，同时拿到"详情 + 五星~一星评分分布"。

    为什么这么设计（实测教训，2026-10-13）：
      * 手机 rexxar 接口 `m.douban.com/rexxar/api/v2/movie/<id>` 会按 IP 限流，
        返回的是 **HTTP 400 + {"msg":"subject_ip_rate_limit","code":1309}**，
        连发约 72 次就中，而且限流期间每条都失败；
      * 电脑端 `movie.douban.com/subject/<id>/` 是另一套配额，实测在被 rexxar
        限流的同时仍然 200，而且**一页里既有全部资料，也有五星~一星占比**；
      * 哈希挑战只解一次，同一会话后续页面基本不再被挑战。
    所以：电脑端一页 = 原来的 detail + rating 两个阶段，请求数直接砍半。
    """
    ids = store.next_movies_full(limit or 10 ** 9)
    log.info("电影资料阶段：待抓 %d 部（每部 1 次请求，含评分分布和热门短评）", len(ids))
    ok = fail = gone = 0
    comment_total = 0
    streak = 0
    for i, mid in enumerate(ids, 1):
        try:
            html = fetcher.pc_subject(mid)
        except ChallengeFailed as e:
            log.error("  %s 解挑战失败：%s", mid, e)
            store.mark_fail(mid, "movie")
            fail += 1
            streak += 1
            if _guard(streak, "电影资料", mid):
                break
            continue
        if not html:
            store.mark_fail(mid, "movie")
            fail += 1
            streak += 1
            if _guard(streak, "电影资料", mid):
                break
            continue
        fields_d = parsers.parse_pc_movie_detail(html)
        if not fields_d.get("title"):
            # 连标题都抠不出来：多半是又拿到挑战页/异常页 —— 记失败，下次重试
            log.warning("  %s 页面里没有标题（长度 %d），记为失败", mid, len(html))
            store.mark_fail(mid, "movie")
            fail += 1
            streak += 1
            if _guard(streak, "电影资料", mid):
                break
            continue
        fields_r, raw = parsers.parse_pc_subject(html)
        fields_d["url"] = fields_d.get("url") or config.URL_PC_SUBJECT.format(id=mid)
        store.save_detail(mid, fields_d, {"source": "pc_subject", **raw})
        if fields_r.get("rating_p5") or fields_r.get("votes"):
            store.save_rating(mid, fields_r, raw)
        else:
            # 有些条目本来就没有评分（没人评过/未上映）。页面上没有就是没有，
            # 但我们确实来看过了，所以照样把 rating_done 标上，不留死循环。
            log.info("  %s 页面上没有评分分布（可能无人评分），照样记录详情", mid)
            store.save_rating(mid, fields_r, raw)
        # 同一个页面里就有热门短评，顺手入库（0 次额外请求）
        cs = parsers.parse_pc_comments(html, mid, limit=config.COMMENTS_PER_MOVIE)
        for c in cs:
            store.add_comment(c)
        if cs:
            store.save_comments_done(mid)
        ok += 1
        comment_total += len(cs)
        streak = 0
        if i % 10 == 0 or i == len(ids):
            log.info("  电影资料 %d/%d 成功 %d 失败 %d 失效 %d 短评 %d",
                     i, len(ids), ok, fail, gone, comment_total)
    log.info("电影资料阶段结束：成功 %d，失败 %d，失效 %d，顺手入库短评 %d 条",
             ok, fail, gone, comment_total)


# ================================================================ 阶段 3：评分分布（老通路，可不用）
def stage_rating(store, fetcher, limit=0):
    ids = store.next_movies("rating", limit or 10 ** 9)
    log.info("评分分布阶段：待抓 %d 部（每部要解一次哈希挑战，速度约 3~5 秒/部）", len(ids))
    ok = fail = 0
    streak = 0
    for i, mid in enumerate(ids, 1):
        try:
            html = fetcher.pc_subject(mid)
            fields, raw = parsers.parse_pc_subject(html)
            if not fields.get("rating_p5") and not fields.get("votes"):
                log.warning("  %s 没解析到评分分布，跳过", mid)
                store.mark_fail(mid, "rating")
                fail += 1
                streak += 1
            else:
                store.save_rating(mid, fields, raw)
                ok += 1
                streak = 0
        except ChallengeFailed as e:
            log.error("  %s 解挑战失败：%s", mid, e)
            store.mark_fail(mid, "rating")
            fail += 1
            streak += 1
        if i % 10 == 0 or i == len(ids):
            log.info("  评分分布 %d/%d 成功 %d 失败 %d", i, len(ids), ok, fail)
        if _guard(streak, "评分分布", mid):
            break
    log.info("评分分布阶段结束：成功 %d，失败 %d", ok, fail)


# ================================================================ 阶段 4：影人
def stage_people(store, fetcher, limit=0, people_limit=0):
    ids = store.next_movies("celeb", limit or 10 ** 9)
    log.info("影人关联阶段：待抓 %d 部电影", len(ids))
    links = 0
    for i, mid in enumerate(ids, 1):
        d = fetcher.movie_celebrities(mid)
        if not d:
            store.mark_fail(mid, "celeb")
            continue
        people = parsers.parse_celebrities(d, mid, config.PEOPLE_PER_MOVIE)
        for p in people:
            store.add_movie_person(mid, p)
            links += 1
        store.save_celeb_done(mid)
        if i % 20 == 0 or i == len(ids):
            log.info("  影人关联 %d/%d，累计关系 %d 条", i, len(ids), links)

    pids = store.next_people(people_limit or 10 ** 9)
    log.info("影人资料阶段：待抓 %d 位", len(pids))
    ok = fail = 0
    for i, pid in enumerate(pids, 1):
        html = fetcher.m_celebrity(pid)
        if not html:
            store.mark_person_fail(pid)
            fail += 1
        else:
            store.save_person(pid, parsers.parse_m_celebrity(html, pid))
            ok += 1
        if i % 20 == 0 or i == len(pids):
            log.info("  影人资料 %d/%d 成功 %d 失败 %d", i, len(pids), ok, fail)
    log.info("影人阶段结束：关系 %d 条，影人资料成功 %d 失败 %d", links, ok, fail)


# ================================================================ 阶段 5：短评
def stage_comments(store, fetcher, limit=0, per_movie=None):
    per_movie = per_movie or config.COMMENTS_PER_MOVIE
    ids = store.next_movies("comments", limit or 10 ** 9)
    log.info("短评阶段：待抓 %d 部电影，每部前 %d 条", len(ids), per_movie)
    total = 0
    fail = 0
    streak = 0
    for i, mid in enumerate(ids, 1):
        d = fetcher.movie_interests(mid, count=per_movie, start=0)
        if not d:
            store.mark_fail(mid, "comments")
            fail += 1
            streak += 1
            if _guard(streak, "短评", mid):
                break
            continue
        cs = parsers.parse_interests(d, mid)
        for c in cs:
            store.add_comment(c)
        total += len(cs)
        store.save_comments_done(mid)
        streak = 0
        if i % 20 == 0 or i == len(ids):
            log.info("  短评 %d/%d，累计 %d 条", i, len(ids), total)
    log.info("短评阶段结束：新增 %d 条，失败 %d 部", total, fail)


# ================================================================ 统计 / 导出
def stage_stats(store):
    c = store.counts()
    print("\n================ 当前进度 ================")
    for k, v in c.items():
        print("  %-14s %s" % (k, v))
    rows = store.conn.execute(
        "SELECT genres, COUNT(*) n FROM movies WHERE genres IS NOT NULL AND genres!=''"
        " GROUP BY genres ORDER BY n DESC LIMIT 1").fetchall()
    print("\n---- 抽样：评分分布已抓的前 5 部 ----")
    for r in store.conn.execute(
            "SELECT id,title,year,rating_num,votes,rating_p5,rating_p4,rating_p3,rating_p2,rating_p1"
            " FROM movies WHERE rating_done=1 LIMIT 5"):
        print("  %s %s(%s) %s分/评价%s人  5星%s%% 4星%s%% 3星%s%% 2星%s%% 1星%s%%"
              % (r["id"], r["title"], r["year"], r["rating_num"], r["votes"],
                 r["rating_p5"], r["rating_p4"], r["rating_p3"], r["rating_p2"], r["rating_p1"]))
    print()
    return c


EXPORT_TABLES = {
    "movies": ("SELECT id,title,original_title,year,subtype,genres,countries,languages,"
               "durations,release_date,pubdate,aka,directors,actors,tags,"
               "rating_value,rating_count,rating_star,rating_num,votes,"
               "rating_p5,rating_p4,rating_p3,rating_p2,rating_p1,"
               "comment_count,review_count,imdb,pc_runtime,honor,card_subtitle,intro,"
               "cover_url,url,detail_at,pc_at FROM movies WHERE detail_done=1"),
    "comments": ("SELECT comment_id,movie_id,content,rating,create_time,ip_location,"
                 "user_id,user_name,votes FROM comments"),
    # movie_people / people 两张表这次不抓、也不导出（用户不需要影人档案）。
    # 想恢复：把下面两行取消注释，并跑 `python crawl.py people`。
    # "movie_people": "SELECT movie_id,people_id,role,name,character,ord FROM movie_people",
    # "people": ("SELECT id,name,latin_name,gender,birthday,born_place,imdb,aka_cn,aka_en,intro"
    #            " FROM people WHERE status='ok'"),
}


def stage_export(store):
    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, sql in EXPORT_TABLES.items():
        rows = store.conn.execute(sql).fetchall()
        if not rows:
            continue
        path = config.EXPORT_DIR / ("%s.csv" % name)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(rows[0].keys())
            for r in rows:
                w.writerow([r[k] for k in r.keys()])
        written.append((path, len(rows)))
        log.info("导出 %s（%d 行）", path.name, len(rows))
    try:
        import openpyxl  # 有就顺手导一份 Excel
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for name, sql in EXPORT_TABLES.items():
            rows = store.conn.execute(sql).fetchall()
            if not rows:
                continue
            ws = wb.create_sheet(name[:31])
            ws.append(list(rows[0].keys()))
            for r in rows:
                ws.append([r[k] for k in r.keys()])
        xlsx = config.EXPORT_DIR / "douban_movies.xlsx"
        wb.save(xlsx)
        written.append((xlsx, 0))
        log.info("导出 Excel：%s", xlsx)
    except ImportError:
        log.info("没装 openpyxl，跳过 Excel 导出（CSV 已经够用，Excel 直接打开 CSV 也行）")
    print("\n导出完成：")
    for p, n in written:
        print("  %s%s" % (p, ("（%d 行）" % n) if n else ""))
    return written


# ================================================================ main
def main():
    ap = argparse.ArgumentParser(description="豆瓣电影数据采集（1500+ 部）")
    ap.add_argument("stage", choices=["discover", "movie", "detail", "rating", "people",
                                      "comments", "all", "stats", "export", "retry"])
    ap.add_argument("--target", type=int, default=0, help="发现阶段的目标电影数")
    ap.add_argument("--max-pages", type=int, default=0, help="每个查询最多翻多少页")
    ap.add_argument("--limit", type=int, default=0, help="本阶段最多处理多少部电影（0=全部）")
    ap.add_argument("--people-limit", type=int, default=0, help="影人资料最多抓多少位")
    ap.add_argument("--per-movie", type=int, default=0, help="每部电影抓多少条短评")
    args = ap.parse_args()

    setup_logging()
    store = Store()

    if args.stage == "stats":
        stage_stats(store)
        store.close()
        return
    if args.stage == "export":
        stage_export(store)
        store.close()
        return
    if args.stage == "retry":
        m, p = store.retry_failed()
        log.info("已把 %d 部电影、%d 位影人的失败计数清零，下次运行会重新尝试它们", m, p)
        stage_stats(store)
        store.close()
        return

    fetcher = Fetcher()
    try:
        fetcher.bootstrap()
    except Exception as e:                        # noqa: BLE001
        # 首页拿不到 cookie（比如正被全站 403）不算致命，继续往下试。
        log.warning("会话初始化失败（不影响继续尝试）：%r", e)
    t0 = time.time()
    waits = 0
    try:
        while True:
            try:
                run_stage(args, store, fetcher)
                break
            except Blocked as e:
                waits += 1
                if waits > config.MAX_BLOCK_WAITS:
                    log.error("已经被限流 %d 次，本次运行收工：%s", waits, e)
                    break
                log.warning("被限流（第 %d 次）：%s", waits, e)
                log.warning("自动睡 %d 分钟后接着爬——长跑时不用人守着；想立刻停就按 Ctrl+C，"
                            "数据都已经在库里。", config.BLOCK_SLEEP // 60)
                time.sleep(config.BLOCK_SLEEP)
                log.info("睡醒了，重新初始化会话（换一套 cookie）后继续……")
                try:
                    fetcher.bootstrap()
                    session_ok = True
                except Exception as be:            # noqa: BLE001
                    session_ok = False
                    log.warning("重新初始化会话失败（不影响继续爬）：%r", be)
                if not session_ok:
                    # 连首页都拿不到 = 整个网络出口被拉黑（跟"单个页面被节流"不是一回事）。
                    # 这时候每 10 分钟探一次只会把惩罚期拖长，所以改用长睡，期间一个请求都不发。
                    log.warning("连豆瓣首页都打不开（整个网络出口被拉黑），改为静默 %d 分钟后再试，"
                                "这段时间程序不发任何请求。", config.BLOCK_SLEEP_SITE // 60)
                    time.sleep(config.BLOCK_SLEEP_SITE)
    except KeyboardInterrupt:
        log.warning("收到 Ctrl+C，已抓到的数据都已提交到数据库，下次运行会自动续爬。")
    except BudgetExceeded as e:
        log.warning("达到本次请求预算：%s", e)
    finally:
        log.info("本次运行 %.1f 分钟 | %s", (time.time() - t0) / 60.0, fetcher.summary())
        store.log_run(args.stage, fetcher.summary())
        stage_stats(store)
        store.close()


def run_stage(args, store, fetcher):
    """按子命令跑对应阶段（被 main 的"熔断就睡一会儿再续"循环反复调用）。"""
    if args.stage in ("discover", "all"):
        stage_discover(store, fetcher, target=args.target or None,
                       max_pages=args.max_pages or None)
    if args.stage in ("movie", "all"):
        stage_movie(store, fetcher, args.limit)
    if args.stage == "detail":
        stage_detail(store, fetcher, args.limit)
    if args.stage == "rating":
        stage_rating(store, fetcher, args.limit)
    if args.stage in ("people",):
        stage_people(store, fetcher, args.limit, args.people_limit)
    if args.stage in ("comments", "all"):
        stage_comments(store, fetcher, args.limit, args.per_movie or None)


if __name__ == "__main__":
    main()
