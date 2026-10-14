# -*- coding: utf-8 -*-
"""
看看抓到的数据长什么样：跑 `python check_data.py`。

它只读数据库，不发任何网络请求，随便跑。
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

conn = sqlite3.connect(config.DB_PATH)
conn.row_factory = sqlite3.Row


def dump(title, sql, n=2, width=1200):
    print("\n========== %s ==========" % title)
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("  （还没数据）")
        return
    print("  共 %d 行，下面展示 %d 行：" % (len(rows), min(n, len(rows))))
    for r in rows[:n]:
        print(json.dumps({k: r[k] for k in r.keys()}, ensure_ascii=False, indent=1)[:width])
        print("  ---")


print("数据库：%s" % config.DB_PATH)
print("\n========== 各阶段进度 ==========")
for label, sql in [
    ("电影总数", "SELECT COUNT(*) c FROM movies"),
    ("  详情已抓", "SELECT COUNT(*) c FROM movies WHERE detail_done=1 AND status='ok'"),
    ("  评分分布已抓", "SELECT COUNT(*) c FROM movies WHERE rating_done=1"),
    ("  影人关联已抓", "SELECT COUNT(*) c FROM movies WHERE celeb_done=1"),
    ("  短评已抓电影", "SELECT COUNT(*) c FROM movies WHERE comments_done=1"),
    ("影人总数", "SELECT COUNT(*) c FROM people"),
    ("  影人资料已抓", "SELECT COUNT(*) c FROM people WHERE status='ok'"),
    ("短评总数", "SELECT COUNT(*) c FROM comments"),
    ("关系总数(movie_people)", "SELECT COUNT(*) c FROM movie_people"),
]:
    print("  %-22s %s" % (label, conn.execute(sql).fetchone()["c"]))

print("\n========== 电影类型分布（前 10） ==========")
for r in conn.execute("SELECT subtype, COUNT(*) n FROM movies GROUP BY subtype ORDER BY n DESC"):
    print("  %-8s %s" % (r["subtype"], r["n"]))

dump("电影（完整字段看一条）", "SELECT * FROM movies WHERE detail_done=1 LIMIT 1")
dump("评分分布（五星~一星占比）",
     "SELECT id,title,year,rating_num,votes,rating_p5,rating_p4,rating_p3,rating_p2,rating_p1,"
     "imdb,pc_runtime FROM movies WHERE rating_done=1 LIMIT 2")
dump("影人", "SELECT id,name,latin_name,gender,birthday,born_place,substr(intro,1,100) intro"
             " FROM people WHERE status='ok' LIMIT 3")
dump("关系", "SELECT * FROM movie_people LIMIT 3")
dump("短评", "SELECT comment_id,movie_id,substr(content,1,60) content,rating,create_time,user_name,"
             "votes FROM comments LIMIT 3")

conn.close()
