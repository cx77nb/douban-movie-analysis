# -*- coding: utf-8 -*-
"""
存储层：SQLite 建表 + 断点续爬状态 + 各类写入。

设计要点（都是上一个项目踩过的坑）：
* 用 SQLite 而不是"打开文件写 w 模式"：每写一条就提交，Ctrl+C / 断电都不丢数据，重跑自动续爬。
* 每个阶段有独立的 done 标记（detail_done / rating_done / celeb_done / comments_done），
  所以可以只补跑某一段，不会重新抓已经抓过的数据。
* 发现阶段把"哪个查询翻到第几页"也存下来（queries 表），重跑时不会重复翻页。
"""
import json
import logging
import sqlite3
import time
from datetime import datetime

import config

log = logging.getLogger("douban.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id              TEXT PRIMARY KEY,
    from_query      TEXT,
    discovered_at   TEXT,
    status          TEXT DEFAULT 'new',      -- new / ok / gone / fail
    fail_count      INTEGER DEFAULT 0,       -- 抓取失败次数（失败不标 done，下次还会重试）
    detail_done     INTEGER DEFAULT 0,
    rating_done     INTEGER DEFAULT 0,
    celeb_done      INTEGER DEFAULT 0,
    comments_done   INTEGER DEFAULT 0,
    title           TEXT,
    original_title  TEXT,
    year            TEXT,
    subtype         TEXT,
    card_subtitle   TEXT,
    genres          TEXT,
    countries       TEXT,
    languages       TEXT,
    durations       TEXT,
    pubdate         TEXT,
    release_date    TEXT,
    aka             TEXT,
    intro           TEXT,
    tags            TEXT,
    directors       TEXT,
    actors          TEXT,
    rating_value    REAL,
    rating_count    INTEGER,
    rating_star     REAL,
    comment_count   INTEGER,
    review_count    INTEGER,
    cover_url       TEXT,
    url             TEXT,
    honor           TEXT,
    is_tv           INTEGER,
    episodes        TEXT,                    -- 电视剧集数
    director_ids    TEXT,                    -- 导演影人 id（电脑端页面 href 里带的）
    actor_ids       TEXT,                    -- 主演影人 id
    detail_at       TEXT,
    rating_p5       REAL,
    rating_p4       REAL,
    rating_p3       REAL,
    rating_p2       REAL,
    rating_p1       REAL,
    rating_num      TEXT,
    votes           INTEGER,
    imdb            TEXT,
    pc_runtime      TEXT,
    pc_release      TEXT,
    pc_aka          TEXT,
    pc_languages    TEXT,
    pc_countries    TEXT,
    pc_at           TEXT,
    detail_json     TEXT,
    pc_json         TEXT
);
CREATE INDEX IF NOT EXISTS idx_movies_status ON movies(status, detail_done, rating_done);

CREATE TABLE IF NOT EXISTS people (
    id          TEXT PRIMARY KEY,
    status      TEXT DEFAULT 'new',
    fail_count  INTEGER DEFAULT 0,
    name        TEXT,
    latin_name  TEXT,
    gender      TEXT,
    birthday    TEXT,
    born_place  TEXT,
    intro       TEXT,
    aka_cn      TEXT,
    aka_en      TEXT,
    imdb        TEXT,
    avatar      TEXT,
    fetched_at  TEXT
);

CREATE TABLE IF NOT EXISTS movie_people (
    movie_id   TEXT,
    people_id  TEXT,
    role       TEXT,
    name       TEXT,
    character  TEXT,
    ord        INTEGER,
    PRIMARY KEY (movie_id, people_id, role)
);

CREATE TABLE IF NOT EXISTS comments (
    comment_id  TEXT PRIMARY KEY,
    movie_id    TEXT,
    content     TEXT,
    rating      REAL,
    create_time TEXT,
    ip_location TEXT,
    user_id     TEXT,
    user_name   TEXT,
    votes       INTEGER,
    raw_json    TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_movie ON comments(movie_id);

CREATE TABLE IF NOT EXISTS queries (
    qkey        TEXT PRIMARY KEY,
    label       TEXT,
    params      TEXT,
    pages_done  INTEGER DEFAULT 0,
    found       INTEGER DEFAULT 0,
    done        INTEGER DEFAULT 0,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    stage       TEXT,
    note        TEXT,
    at          TEXT
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, path=None):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = str(path or config.DB_PATH)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """给老的数据库补上后来新增的列（不用删库重来）。"""
        add = {
            "movies": [("fail_count", "INTEGER DEFAULT 0"),
                       ("episodes", "TEXT"),
                       ("director_ids", "TEXT"),
                       ("actor_ids", "TEXT")],
            "people": [("fail_count", "INTEGER DEFAULT 0")],
        }
        for table, cols in add.items():
            have = [r[1] for r in self.conn.execute("PRAGMA table_info(%s)" % table)]
            for name, decl in cols:
                if name not in have:
                    self.conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, decl))
                    log.info("数据库补列：%s.%s", table, name)

    def close(self):
        self.conn.commit()
        self.conn.close()

    def log_run(self, stage, note=""):
        self.conn.execute("INSERT INTO run_log(stage, note, at) VALUES (?,?,?)",
                          (stage, note, now()))
        self.conn.commit()

    # ------------------------------------------------------------ 发现阶段
    def add_discovered(self, movie_id, from_query=""):
        """新发现的电影入队；已存在则什么都不做（去重就靠主键）。"""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO movies(id, from_query, discovered_at) VALUES (?,?,?)",
            (str(movie_id), from_query, now()))
        return cur.rowcount > 0

    def commit(self):
        self.conn.commit()

    # ------------------------------------------------------------ 队列取数
    def next_movies(self, stage, limit):
        """取这个阶段还没成功抓到、且失败次数没超上限的电影。
        失败的排在最后（fail_count 小的优先），避免个别抓不动的条目反复挡在前头。"""
        where = {
            "detail": "detail_done=0 AND status!='gone'",
            "rating": "detail_done=1 AND rating_done=0 AND status='ok'",
            "celeb": "detail_done=1 AND celeb_done=0 AND status='ok'",
            "comments": "detail_done=1 AND comments_done=0 AND status='ok'",
        }[stage]
        rows = self.conn.execute(
            "SELECT id FROM movies WHERE %s AND fail_count < ?"
            " ORDER BY fail_count, id LIMIT ?" % where,
            (config.MAX_FAIL_PER_ITEM, limit)).fetchall()
        return [r["id"] for r in rows]

    def next_people(self, limit):
        rows = self.conn.execute(
            "SELECT id FROM people WHERE status='new' AND fail_count < ?"
            " ORDER BY fail_count, id LIMIT ?",
            (config.MAX_FAIL_PER_ITEM, limit)).fetchall()
        return [r["id"] for r in rows]

    def next_movies_full(self, limit):
        """"一部电影一页"阶段（电脑端详情页）要处理的队列：详情或评分分布缺任意一项。"""
        rows = self.conn.execute(
            "SELECT id FROM movies WHERE status!='gone' AND (detail_done=0 OR rating_done=0)"
            " AND fail_count < ? ORDER BY fail_count, detail_done, id LIMIT ?",
            (config.MAX_FAIL_PER_ITEM, limit)).fetchall()
        return [r["id"] for r in rows]

    def count_retryable(self):
        """当前还有多少条是"失败但可以重试"的（想让它们立刻重试就跑 crawl.py retry）。"""
        m = self.conn.execute(
            "SELECT COUNT(*) c FROM movies WHERE fail_count>0 AND fail_count<?",
            (config.MAX_FAIL_PER_ITEM,)).fetchone()["c"]
        p = self.conn.execute(
            "SELECT COUNT(*) c FROM people WHERE fail_count>0 AND fail_count<?",
            (config.MAX_FAIL_PER_ITEM,)).fetchone()["c"]
        return m, p

    def retry_failed(self):
        """把所有失败计数清零，让下一次运行重新尝试这些条目。"""
        n1 = self.conn.execute("UPDATE movies SET fail_count=0 WHERE fail_count>0").rowcount
        n2 = self.conn.execute(
            "UPDATE people SET fail_count=0, status='new' WHERE fail_count>0 OR status='fail'"
        ).rowcount
        self.conn.commit()
        return n1, n2

    # ------------------------------------------------------------ 详情写入
    def save_detail(self, movie_id, fields, raw):
        cols = ["status", "detail_done", "detail_at", "detail_json", "fail_count"] + list(fields)
        vals = ["ok", 1, now(), json.dumps(raw, ensure_ascii=False), 0] + list(fields.values())
        sets = ", ".join("%s=?" % c for c in cols)
        self.conn.execute("UPDATE movies SET %s WHERE id=?" % sets, vals + [movie_id])
        self.conn.commit()

    def mark_gone(self, movie_id, note="404"):
        self.conn.execute(
            "UPDATE movies SET status='gone', detail_done=1, detail_json=? WHERE id=?",
            (note, movie_id))
        self.conn.commit()

    def mark_fail(self, movie_id, stage=""):
        """抓取失败：**不标 done**，只累加失败次数 —— 这样下次运行还会重试它。
        （对照老项目：失败也当成"抓过了"跳过，于是数据永久缺失。）"""
        self.conn.execute("UPDATE movies SET fail_count=fail_count+1 WHERE id=?", (movie_id,))
        self.conn.commit()

    def save_rating(self, movie_id, fields, raw):
        """写入电脑端详情页补充出来的字段（评分分布、IMDb 编号、片长……）。"""
        cols = ["rating_done", "pc_at", "fail_count"] + list(fields) + ["pc_json"]
        vals = [1, now(), 0] + list(fields.values()) + [json.dumps(raw, ensure_ascii=False)]
        sets = ", ".join("%s=?" % c for c in cols)
        self.conn.execute("UPDATE movies SET %s WHERE id=?" % sets, vals + [movie_id])
        self.conn.commit()

    def save_celeb_done(self, movie_id):
        self.conn.execute("UPDATE movies SET celeb_done=1 WHERE id=?", (movie_id,))
        self.conn.commit()

    def save_comments_done(self, movie_id):
        self.conn.execute("UPDATE movies SET comments_done=1 WHERE id=?", (movie_id,))
        self.conn.commit()

    # ------------------------------------------------------------ 影人
    def add_movie_person(self, movie_id, p):
        """p 是 parsers.parse_celebrities 返回的 dict。同时把影人名字/外文名/头像补进 people 表。"""
        self.conn.execute(
            "INSERT OR IGNORE INTO movie_people(movie_id, people_id, role, name, character, ord)"
            " VALUES (?,?,?,?,?,?)",
            (movie_id, p["id"], p["role"], p["name"], p["character"], p["ord"]))
        self.conn.execute(
            "INSERT INTO people(id, name, latin_name, avatar) VALUES (?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            "   name       = COALESCE(people.name, excluded.name),"
            "   latin_name = COALESCE(people.latin_name, excluded.latin_name),"
            "   avatar     = COALESCE(people.avatar, excluded.avatar)",
            (p["id"], p["name"], p.get("latin_name"), p.get("avatar")))

    def save_person(self, people_id, fields):
        cols = list(fields) + ["fail_count"]
        sets = ", ".join("%s=?" % c for c in cols)
        self.conn.execute("UPDATE people SET status='ok', fetched_at=?, %s WHERE id=?" % sets,
                          [now()] + list(fields.values()) + [0, people_id])
        self.conn.commit()

    def mark_person_fail(self, people_id):
        """失败先不判死刑：累加次数，超过上限才标 fail（可以用 crawl.py retry 复活）。"""
        self.conn.execute(
            "UPDATE people SET fail_count=fail_count+1,"
            " status=CASE WHEN fail_count+1 >= ? THEN 'fail' ELSE 'new' END,"
            " fetched_at=? WHERE id=?",
            (config.MAX_FAIL_PER_ITEM, now(), people_id))
        self.conn.commit()

    # ------------------------------------------------------------ 短评
    def add_comment(self, c):
        self.conn.execute(
            "INSERT OR IGNORE INTO comments(comment_id, movie_id, content, rating,"
            " create_time, ip_location, user_id, user_name, votes, raw_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (c["comment_id"], c["movie_id"], c["content"], c["rating"], c["create_time"],
             c["ip_location"], c["user_id"], c["user_name"], c["votes"],
             json.dumps(c.get("raw"), ensure_ascii=False)))
        self.conn.commit()

    # ------------------------------------------------------------ 查询进度
    def query_state(self, qkey):
        row = self.conn.execute("SELECT * FROM queries WHERE qkey=?", (qkey,)).fetchone()
        if row:
            return dict(row)
        return {"qkey": qkey, "pages_done": 0, "found": 0, "done": 0}

    def save_query_state(self, qkey, label, params, pages_done, found, done):
        self.conn.execute(
            "INSERT INTO queries(qkey, label, params, pages_done, found, done, updated_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(qkey) DO UPDATE SET pages_done=excluded.pages_done,"
            " found=excluded.found, done=excluded.done, updated_at=excluded.updated_at",
            (qkey, label, json.dumps(params, ensure_ascii=False), pages_done, found,
             1 if done else 0, now()))
        self.conn.commit()

    # ------------------------------------------------------------ 统计
    def counts(self):
        q = self.conn.execute
        out = {}
        out["电影总数"] = q("SELECT COUNT(*) c FROM movies").fetchone()["c"]
        out["详情已抓"] = q("SELECT COUNT(*) c FROM movies WHERE detail_done=1 AND status='ok'"
                            ).fetchone()["c"]
        out["评分分布已抓"] = q("SELECT COUNT(*) c FROM movies WHERE rating_done=1"
                                ).fetchone()["c"]
        out["影人关联已抓"] = q("SELECT COUNT(*) c FROM movies WHERE celeb_done=1"
                                ).fetchone()["c"]
        out["短评已抓电影"] = q("SELECT COUNT(*) c FROM movies WHERE comments_done=1"
                                ).fetchone()["c"]
        out["已失效(404)"] = q("SELECT COUNT(*) c FROM movies WHERE status='gone'"
                              ).fetchone()["c"]
        out["影人总数"] = q("SELECT COUNT(*) c FROM people").fetchone()["c"]
        out["影人资料已抓"] = q("SELECT COUNT(*) c FROM people WHERE status='ok'"
                                ).fetchone()["c"]
        out["短评总数"] = q("SELECT COUNT(*) c FROM comments").fetchone()["c"]
        out["发现的查询数"] = q("SELECT COUNT(*) c FROM queries").fetchone()["c"]
        mr, pr = self.count_retryable()
        out["待重试(电影)"] = mr
        out["待重试(影人)"] = pr
        return out
