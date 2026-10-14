# -*- coding: utf-8 -*-
"""看门狗：每 15 分钟记录一次采集进度，发现停滞就报警。
只在日志文件里追加，不碰数据库，不向豆瓣发任何请求。
"""
import datetime
import io
import os
import re
import sqlite3
import sys
import time

ROOT = r"D:\App\study_data\douban_movie_project"
DB = os.path.join(ROOT, "data", "douban.db")
LOG_DIR = os.path.join(ROOT, "logs")
WATCH_LOG = os.path.join(LOG_DIR, "watch.log")

CHECK_EVERY = 900          # 每 15 分钟看一次
MAX_CHECKS = 36            # 最多看 9 小时
STALL_LIMIT = 4            # 连续 4 次（1 小时）没进展就算停滞


def now():
    return datetime.datetime.now().strftime("%H:%M:%S")


def crawl_log_path():
    """采集日志按日期命名（crawl_YYYYMMDD.log），始终跟最新那份。"""
    try:
        names = [n for n in os.listdir(LOG_DIR) if n.startswith("crawl_") and n.endswith(".log")]
    except OSError:
        return ""
    if not names:
        return ""
    return max((os.path.join(LOG_DIR, n) for n in names), key=os.path.getmtime)


def counts():
    conn = sqlite3.connect(DB)
    try:
        return (
            conn.execute("SELECT COUNT(*) FROM movies WHERE detail_done=1").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM movies WHERE rating_done=1").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM movies WHERE fail_count>0").fetchone()[0],
        )
    finally:
        conn.close()


def last_crawl_lines(n=2):
    path = crawl_log_path()
    if not path:
        return []
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return [x.rstrip() for x in f.readlines()[-n:]]
    except OSError:
        return []


def read_log():
    path = crawl_log_path()
    if not path:
        return ""
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def crawl_finished(baseline):
    """电影阶段结束语在本次启动前出现过的次数作为基线，变多才算这次跑完。"""
    return read_log().count("电影资料阶段结束") > baseline


def main():
    last_detail = -1
    stall = 0
    baseline = read_log().count("电影资料阶段结束")
    with io.open(WATCH_LOG, "a", encoding="utf-8") as out:
        out.write("\n===== 看门狗启动 %s（已完成阶段次数基线=%d）=====\n" % (now(), baseline))
        out.flush()
        for i in range(MAX_CHECKS):
            try:
                detail, rating, comments, failed = counts()
            except Exception as exc:                      # noqa: BLE001
                out.write("%s  读取数据库失败：%r\n" % (now(), exc))
                out.flush()
                time.sleep(CHECK_EVERY)
                continue
            flag = ""
            if detail == last_detail:
                stall += 1
                if stall >= STALL_LIMIT:
                    flag = "  <<< 停滞 %d 次检查（约 %d 分钟无新电影）" % (stall, stall * 15)
            else:
                stall = 0
            last_detail = detail
            line = ("%s  详情 %4d | 评分分布 %4d | 短评 %5d | 有失败标记 %2d%s"
                    % (now(), detail, rating, comments, failed, flag))
            out.write(line + "\n")
            out.flush()
            if flag:
                for x in last_crawl_lines(3):
                    out.write("        日志：%s\n" % x)
                out.flush()
            if crawl_finished(baseline):
                out.write("%s  日志显示采集/导出已完成，看门狗退出。\n" % now())
                out.flush()
                return
            time.sleep(CHECK_EVERY)
        out.write("%s  看满 %d 次，退出。\n" % (now(), MAX_CHECKS))
        out.flush()


if __name__ == "__main__":
    main()
