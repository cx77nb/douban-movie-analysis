# -*- coding: utf-8 -*-
"""
网络层：会话、限速、重试退避、哈希挑战求解，以及所有数据接口的封装。

对外只需要一个类：Fetcher
    f = Fetcher()
    f.discover(genres="剧情", range="9,10", start=0)   -> 电影列表（20 条/页）
    f.movie_detail("1292052")                          -> 电影详情 dict
    f.movie_celebrities("1292052")                     -> 影人 dict
    f.movie_interests("1292052", count=5)              -> 短评 dict
    f.pc_subject("1292052")                            -> 电脑端详情页 HTML（自动解挑战）
    f.m_celebrity("1047973")                           -> 手机端影人页 HTML
"""
import hashlib
import html as html_mod
import http.cookiejar
import json
import logging
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import config

log = logging.getLogger("douban.api")


class ChallengeFailed(Exception):
    """解豆瓣哈希挑战失败。"""


class Blocked(Exception):
    """短时间内连续被 403/429，判断为被限流，主动停下来保护账号/IP。"""


class BudgetExceeded(Exception):
    """超过本次运行的请求预算。"""


def _is_rate_limit(body, code):
    """判断这个响应是不是豆瓣的"IP 配额限流"。

    实测特征（2026 年）：HTTP **400** + 正文
        {"msg": "subject_ip_rate_limit", "code": 1309,
         "localized_message": "您所在的网络存在异常，请登录后重试。"}
    注意是 400 不是 403 —— 区别对待它是整个项目最关键的一处判断。
    403/429 同样按限流处理。
    """
    if code in (403, 429):
        return True
    if not body:
        return False
    if "subject_ip_rate_limit" in body or "ip_rate_limit" in body:
        return True
    return '"code":1309' in body.replace(" ", "")


class Fetcher:
    # 电脑端页面的正常大小是 100KB 上下；低于这个值一定是异常页（实测限流时给 1041 字节）
    SHORT_PAGE = 3000

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
        self._last_call = {}          # 每类请求的上次时间，用于限速
        self.request_count = 0        # 本次运行已发出的请求数
        self.solved_challenges = 0
        self.consec_403 = 0           # 连续 403/429 计数，用于"被限流就停"的熔断
        self.rate_limited = 0         # 连续被豆瓣"IP 配额限流"（400/code 1309）的次数
        self.short_hits = 0           # 电脑端返回空壳页的次数（疑似限流）
        self.kind_calls = {}          # 每类请求累计次数，用于"每 N 次休息一次"
        self._uas = {}                # 每类请求固定用的 UA（同一会话不许换 UA，见 _headers）
        self.stats = {"ok": 0, "empty": 0, "challenge": 0, "http_error": 0,
                      "failed": 0, "rate_limited": 0}

    # ------------------------------------------------------------ 内部工具
    def _wait(self, kind):
        lo, hi = {
            "pc": config.DELAY_PC,
            "rexxar": getattr(config, "DELAY_REXXAR", config.DELAY_API),
        }.get(kind, config.DELAY_API)
        gap = random.uniform(lo, hi)
        prev = self._last_call.get(kind, 0.0)
        delta = prev + gap - time.time()
        if delta > 0:
            time.sleep(delta)
        self._last_call[kind] = time.time()

    def _headers(self, kind, referer=None, form=False):
        # 【实测教训】每次请求都随机换 UA，会让豆瓣每次都把我们当"新客户端"，
        # 于是每一页都要先解一次哈希挑战（请求数直接翻倍、速度掉一半）。
        # 同一个会话就该用同一个 UA —— 这里按类别固定下来，只随机一次。
        if kind not in self._uas:
            self._uas[kind] = random.choice(config.UA_PC if kind == "pc" else config.UA_MOBILE)
        ua = self._uas[kind]
        h = {
            "User-Agent": ua,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        }
        if form:
            h["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
            h["Content-Type"] = "application/x-www-form-urlencoded"
            # 注意：这里刻意不发 Origin。实测带上 Origin 会让 sec.douban.com/c 直接回 403。
        elif kind == "pc":
            h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        else:
            h["Accept"] = "application/json, text/plain, */*"
        if referer:
            h["Referer"] = referer
        return h

    def _fetch_once(self, url, kind, referer, data):
        headers = self._headers(kind, referer=referer, form=bool(data))
        body = data if isinstance(data, bytes) else None
        req = urllib.request.Request(url, data=body, headers=headers)
        # 分批休息：某类接口每发 N 次就强制睡一会儿，别去撞豆瓣的配额。
        br = getattr(config, "BURST_REST", {}).get(kind)
        if br:
            every, rest = br
            n = self.kind_calls.get(kind, 0) + 1
            self.kind_calls[kind] = n
            if every and n % every == 0:
                log.info("%s 接口已连发 %d 次，按配额策略休息 %d 秒（别撞限流）", kind, n, rest)
                time.sleep(rest)
        self._wait(kind)
        self.request_count += 1
        if config.MAX_REQUESTS_PER_RUN and self.request_count > config.MAX_REQUESTS_PER_RUN:
            raise BudgetExceeded("已超过 MAX_REQUESTS_PER_RUN=%d" % config.MAX_REQUESTS_PER_RUN)
        with self.opener.open(req, timeout=config.HTTP_TIMEOUT) as resp:
            raw = resp.read()
            return resp.status, raw.decode("utf-8", "replace"), resp.geturl()

    def fetch(self, url, kind="api", referer=None, form=None, allow_empty=True):
        """带重试与退避的 GET/POST。返回 (status, text, final_url)。"""
        data = urllib.parse.urlencode(form).encode("utf-8") if form else None
        last_err = None
        for attempt in range(1, config.MAX_RETRY + 1):
            try:
                st, text, final = self._fetch_once(url, kind, referer, data)
                self.consec_403 = 0
                self.rate_limited = 0      # 只要有一条成功，就认为限流窗口已过去
                return st, text, final
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                self.stats["http_error"] += 1
                try:
                    body = e.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    body = ""
                # 【关键修复】豆瓣对手机接口的 IP 配额返回的是 HTTP 400 + code 1309，
                # 不是 403。老版本把 400 当"确定性错误不重试"，于是限流期间上千部电影
                # 被静默刷成失败。这里必须先认限流，再谈别的 400。
                if _is_rate_limit(body, e.code):
                    self.rate_limited += 1
                    self.stats["rate_limited"] += 1
                    if self.rate_limited > config.RATE_LIMIT_RETRY:
                        raise Blocked(
                            "被豆瓣按 IP 限流（HTTP %s：%s）。这是整个网络出口的配额，"
                            "不是某一条的问题，所以主动停下。等 30~60 分钟再重跑同一条"
                            "命令即可续爬，已抓到的数据都在库里。"
                            % (e.code, (body or "")[:120]))
                    log.warning("被限流（HTTP %s：%s），等 %d 秒后重试同一条",
                                e.code, (body or "")[:100], config.RATE_LIMIT_WAIT)
                    time.sleep(config.RATE_LIMIT_WAIT)
                    continue
                # 404/400/410 之类的确定性错误：重试也没用，直接返回给上层判断
                if e.code in (404, 400, 410):
                    return e.code, body, url
                if e.code in (403, 429):
                    self.consec_403 += 1
                    if self.consec_403 >= config.BLOCK_THRESHOLD:
                        raise Blocked(
                            "连续 %d 次 %s，判断为被限流，已主动停止。"
                            "请等 30~60 分钟再跑，或把 config.DELAY_API 调大。"
                            % (self.consec_403, e.code))
                    wait = config.BACKOFF_403
                else:
                    wait = config.BACKOFF[min(attempt - 1, len(config.BACKOFF) - 1)]
                log.warning("HTTP %s on %s（第 %d 次），等 %ds 重试", e.code, url, attempt, wait)
                time.sleep(wait)
            except BudgetExceeded:
                raise
            except Blocked:
                raise
            except Exception as e:  # noqa: BLE001
                last_err = repr(e)
                self.stats["failed"] += 1
                wait = config.BACKOFF[min(attempt - 1, len(config.BACKOFF) - 1)]
                log.warning("请求失败 %s（第 %d 次）：%s，等 %ds", url, attempt, e, wait)
                time.sleep(wait)
        log.error("放弃 %s：%s", url, last_err)
        return None, "", url

    # ------------------------------------------------------------ 启动
    def bootstrap(self):
        """先访问一次首页，拿到 bid / ll 这两个匿名 cookie。"""
        st, _, _ = self.fetch(config.URL_HOME, kind="pc")
        cookies = ", ".join("%s=%s" % (c.name, c.value) for c in self.jar)
        log.info("会话初始化 status=%s cookies=[%s]", st, cookies)

    # ------------------------------------------------------------ 接口 1：发现
    def discover(self, **params):
        """电影列表 JSON 接口。返回 data 列表（每页 20 条，被限速时会返回空列表）。"""
        url = config.URL_SEARCH_API + "?" + urllib.parse.urlencode(params)
        st, text, _ = self.fetch(url, kind="api", referer="https://movie.douban.com/explore")
        if st != 200 or not text:
            return []
        try:
            data = json.loads(text).get("data") or []
        except ValueError:
            log.warning("列表接口返回非 JSON：%s", text[:120])
            return []
        if not data:
            self.stats["empty"] += 1
        else:
            self.stats["ok"] += 1
        return data

    # ------------------------------------------------------------ 接口 2：详情 JSON
    def movie_detail(self, movie_id):
        url = config.URL_REXXAR_MOVIE.format(id=movie_id)
        st, text, _ = self.fetch(url, kind="rexxar",
                                 referer="https://m.douban.com/movie/subject/%s/" % movie_id)
        if st == 404:
            return {"__gone__": True}
        if st != 200 or not text:
            # 一定要喊出来：静默失败正是"1000 部被刷成失败却没人发现"的原因
            log.warning("详情接口异常：id=%s status=%s 正文前 120 字=%r",
                        movie_id, st, (text or "")[:120])
            return None
        try:
            d = json.loads(text)
        except ValueError:
            log.warning("详情接口返回非 JSON：id=%s %r", movie_id, text[:120])
            return None
        if not isinstance(d, dict) or "title" not in d:
            log.warning("详情接口缺少 title：id=%s 键=%s", movie_id,
                        list(d)[:8] if isinstance(d, dict) else type(d).__name__)
            return None
        self.stats["ok"] += 1
        return d

    # ------------------------------------------------------------ 接口 3：影人 JSON
    def movie_celebrities(self, movie_id):
        url = config.URL_REXXAR_CELEBS.format(id=movie_id)
        st, text, _ = self.fetch(url, kind="rexxar",
                                 referer="https://m.douban.com/movie/subject/%s/" % movie_id)
        if st != 200 or not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    # ------------------------------------------------------------ 接口 4：短评 JSON
    def movie_interests(self, movie_id, count=5, start=0):
        url = config.URL_REXXAR_INTERESTS.format(id=movie_id, count=count, start=start)
        st, text, _ = self.fetch(url, kind="rexxar",
                                 referer="https://m.douban.com/movie/subject/%s/" % movie_id)
        if st != 200 or not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    # ------------------------------------------------------------ 接口 5：电脑端详情页（需解挑战）
    @staticmethod
    def _is_challenge(text):
        return bool(text) and 'id="sec"' in text and "sha512" in text

    def _solve_challenge(self, page, target_url):
        """豆瓣的哈希现金挑战：找一个 nonce，使 sha512(cha+nonce) 的前 4 位是 0。
        解出来以后 POST 到 sec.douban.com/c，返回的就是原本想访问的那个页面。"""
        def field(name):
            m = re.search(r'id="%s"[^>]*value="([^"]*)"' % name, page)
            return html_mod.unescape(m.group(1)) if m else None

        tok, cha, red = field("tok"), field("cha"), field("red")
        if not (tok and cha):
            raise ChallengeFailed("挑战页里找不到 tok/cha 字段")
        difficulty = 4
        m = re.search(r"process\(\s*cha\s*,\s*(\d+)", page)
        if m:
            difficulty = int(m.group(1))
        prefix = "0" * difficulty
        nonce = 0
        t0 = time.time()
        while True:
            nonce += 1
            digest = hashlib.sha512((cha + str(nonce)).encode("utf-8")).hexdigest()
            if digest.startswith(prefix):
                break
        log.info("解挑战成功：nonce=%d，难度=%d，耗时 %.2fs", nonce, difficulty, time.time() - t0)
        st, text, _ = self.fetch(config.URL_SEC_SUBMIT, kind="pc", referer=target_url,
                                 form={"tok": tok, "cha": cha, "sol": str(nonce),
                                       "red": red or target_url})
        self.solved_challenges += 1
        self.stats["challenge"] += 1
        return st, text

    def pc_page(self, url, referer=None):
        """取电脑端 HTML 页面；遇到挑战自动解一次再取。

        实测豆瓣有时会返回一个 1KB 左右的空壳页（既没有内容也不是挑战页）——
        连续出现就说明又被限流了，这里按"等一会儿再试一次，还不行就熔断"处理。
        """
        for attempt in (0, 1):
            st, text, final = self.fetch(url, kind="pc", referer=referer or config.URL_HOME)
            if self._is_challenge(text):
                # 挑战页实际来自 sec.douban.com，POST 的 Referer 必须是这个最终地址
                log.info("遇到哈希挑战：%s（挑战页来自 %s）", url, final)
                st2, text2 = self._solve_challenge(text, final or url)
                # POST 的响应通常就是目标页面；不像就再正常 GET 一次
                if text2 and not self._is_challenge(text2) and len(text2) > 5000:
                    return text2
                st, text, final = self.fetch(url, kind="pc", referer=referer or config.URL_HOME)
                if self._is_challenge(text):
                    raise ChallengeFailed("解挑战之后仍然被挑战：%s" % url)
            if text is not None and len(text) >= self.SHORT_PAGE:
                return text
            # ——空壳页：留下原文，方便判断到底是限流页还是改版页——
            self.short_hits += 1
            if self.short_hits <= 5:
                p = config.LOG_DIR / ("short_page_%d.html" % self.short_hits)
                try:
                    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
                    p.write_text(text or "", encoding="utf-8")
                except OSError:
                    p = "(存不下)"
                log.warning("收到空壳页：%s 只有 %d 字节，不是挑战页。原文已存 %s，开头 300 字：%r",
                            url, len(text or ""), p, (text or "")[:300])
            if attempt == 0:
                log.warning("等 %d 秒后重试同一条（豆瓣大概又在限流了）", config.SHORT_PAGE_WAIT)
                time.sleep(config.SHORT_PAGE_WAIT)
                try:
                    self.bootstrap()     # 换一套匿名 cookie（ll/bid），也许能重新起算
                except Exception as e:   # noqa: BLE001
                    log.warning("重新初始化会话失败（不影响继续重试）：%r", e)
        raise Blocked("连续拿到空壳页（最后一条 %s），判定被豆瓣限流；已抓数据都在库里，"
                      "过 30~60 分钟重跑同一条命令即可续爬" % url)

    def pc_subject(self, movie_id):
        return self.pc_page(config.URL_PC_SUBJECT.format(id=movie_id),
                            referer="https://movie.douban.com/top250")

    # ------------------------------------------------------------ 接口 6：手机端影人页
    def m_celebrity(self, celeb_id):
        url = config.URL_M_CELEBRITY.format(id=celeb_id)
        st, text, _ = self.fetch(url, kind="api", referer="https://m.douban.com/")
        if st != 200:
            return None
        return text

    # ------------------------------------------------------------ 收尾
    def summary(self):
        return ("请求 %d 次 | 解挑战 %d 次 | 被限流 %d 次 | %s"
                % (self.request_count, self.solved_challenges,
                   self.stats.get("rate_limited", 0), self.stats))
