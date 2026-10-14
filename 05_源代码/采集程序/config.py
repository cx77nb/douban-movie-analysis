# -*- coding: utf-8 -*-
"""
配置中心：所有可调参数都在这里，改这个文件就够了，不用动代码。

【本项目的实测结论（2026 年探测，见 README 的"接口分析"一节）】
1) 电影"发现"（拿一长串电影 id）：用电脑端列表 JSON 接口，免登录、免解挑战、速度快。
2) 电影"详情"：用手机端 rexxar JSON 接口，免登录、免解挑战，返回 30+ 字段。
3) 评分分布（5星~1星占比）：只有电脑端 HTML 页面有，需要先解豆瓣的哈希挑战（代码自动解）。
4) 影人资料：用手机端影人页面 HTML，免登录、免解挑战。
5) 短评：用手机端 rexxar interests 接口，免登录，但每个电影最多只能翻到 100 条左右。
"""
from pathlib import Path

# ---------------------------------------------------------------- 目录
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "export"
DB_PATH = DATA_DIR / "douban.db"

# ---------------------------------------------------------------- 目标规模
# 目标电影数。用户 2026-xx 定：先做 1000 部左右（够撑起资料库/评分/影人/短评四张表，
# 又能把总请求量控制在可接受范围）。想加量：直接把这个数调大，discover 会继续往下翻页。
TARGET_MOVIES = 1000

# 短评：每部电影抓前几条（rexxar 接口每次最多给 100 条左右）
COMMENTS_PER_MOVIE = 5

# 每部电影最多取多少个影人（导演优先，然后按演员表顺序）
# 【2026 决定】用户不需要单独的影人档案表，所以推荐的流水线里**不跑 people 阶段**，
# 这个值只在你想单独跑 `python crawl.py people` 时才起作用（导演/主演的姓名仍然在
# movies 表的 directors / actors 两列里，detail 阶段就会抓到）。
PEOPLE_PER_MOVIE = 6

# ---------------------------------------------------------------- 限速（秒）
# 随机取值区间。豆瓣对同一 IP 的请求频率很敏感，这两个值不要调小。
# 【实测】用 (1.2, 2.4)/(2.0, 3.5) 连续跑约 90 次请求（4 分钟内）后，豆瓣开始对
# 本机 IP 全站返回 403。所以默认值已经调成更保守的一档；再被 403 就继续往上调。
DELAY_API = (3.0, 6.0)      # 列表接口 movie.douban.com/j/...（实测很宽容）
DELAY_REXXAR = (6.0, 9.0)   # 手机接口 m.douban.com/rexxar/...（**配额最紧**）
DELAY_PC = (6.0, 9.0)       # 电脑端 HTML 页面（需解哈希挑战，**另有腾讯验证码墙**）

# 【实测记录 · 务必先读】手机 rexxar 接口在连续发出约 72 次请求后，开始对整台 IP 返回：
#     HTTP 400  {"msg":"subject_ip_rate_limit","code":1309,
#                "localized_message":"您所在的网络存在异常，请登录后重试。"}
# 注意它是 **400 而不是 403**！早期版本的 fetch() 把 400 当成"确定性错误、不重试"直接放过，
# 于是限流期间 500 多部电影被静默标记成失败。下面三个参数就是为它准备的。
RATE_LIMIT_WAIT = 300       # 撞到限流后先等 5 分钟，再重试同一条请求
RATE_LIMIT_RETRY = 1        # 同一条请求被限流后最多重试几次；重试还限流就整体停下（熔断）

# 主动"分批休息"：某类接口每发 N 次请求就强制睡 M 秒，模拟人的节奏，别去撞配额。
# 键是请求类型（rexxar=手机接口，pc=电脑端页面），值是 (每多少次, 休息多少秒)。
BURST_REST = {
    "rexxar": (40, 300),    # 手机接口：每 40 次休息 5 分钟
    "pc": (9, 180),         # 电脑端页面：每 9 个页面主动休息 3 分钟（见下面的"验证码墙"说明）
}

# 【实测记录 · 第三种限流长相（最重要的一条）】电脑端 movie.douban.com/subject/<id>/ 在
# 连续抓约 **10 个页面**（间隔 8 秒也一样）之后，会返回一个 1041 字节的页面：
#     <title>禁止访问</title> … "你访问豆瓣的方式有点像机器人程序。为了保护用户的数据，
#     请向我们证明你是人类" … 腾讯 TCaptcha（appid 2003459237）→ POST /misc/sorry
# 这是**人机验证墙**，拿不到任何数据，也没有办法用代码解（不是那个 sha512 哈希题）。
# 实测它会在 2~3 分钟后自行解除，然后又能抓 ~10 个页面 —— 所以它是"配额 + 缓慢回血"，
# 稳定的可持续速度大约是 **每分钟 2~3 个页面**。因此：
#   · 别去撞墙（撞了要多付 3 分钟），改成主动节奏：每抓 9 个页面就休息 3 分钟
#     （BURST_REST["pc"] = (9, 180)），页面之间的间隔用 DELAY_PC（6~9 秒）就够；
#   · 万一还是撞墙：pc_page 会睡 SHORT_PAGE_WAIT 再试一次，还不行就熔断、
#     由 main 睡 BLOCK_SLEEP 续爬；
#   · 全量 1000 部按这个节奏大约要 8~10 小时（可以挂着过夜跑）。
# 【实测记录 · 第二种限流长相（比 400 更隐蔽）】电脑端详情页被限流时返回一个 1KB 空壳页，
# HTTP 仍然是 200、也没有电影资料，代码里用"页面长度 < SHORT_PAGE(3000)"来识别它。
SHORT_PAGE_WAIT = 180       # 拿到空壳页（禁访页）后先等 3 分钟再试同一条
BLOCK_SLEEP = 600           # 熔断后自动睡 10 分钟再续爬（长跑时不用人守着）
# 【实测记录 · 第四种惩罚：全站 403】短时间猛探（几百次请求）之后，豆瓣会对整台 IP
# 返回 403，连 https://movie.douban.com/ 首页都是 403，持续十几分钟到一小时不等。
# 这种情况下继续每 10 分钟探一次只会把惩罚期拖长，所以只要"重新初始化会话"（打首页）
# 也失败，就改睡 BLOCK_SLEEP_SITE，期间一个请求都不发。
BLOCK_SLEEP_SITE = 1800     # 整个出口被拉黑时静默 30 分钟
MAX_BLOCK_WAITS = 40        # 一次运行最多自动睡这么多轮

HTTP_TIMEOUT = 30         # 单次请求超时
MAX_RETRY = 3             # 每个请求最多尝试次数
BACKOFF = (20, 45, 90)    # 普通失败（超时/连接错误）后的等待秒数
BACKOFF_403 = 60          # 被 403/429 后的等待秒数（单独一档，别等太久）

# 熔断：连续这么多次 403/429/限流 就认为被限流，直接停下来（保护你的 IP），
# 而不是继续硬冲。停下来后等 30~60 分钟再跑，数据不会丢。
BLOCK_THRESHOLD = 6

# 一个阶段里"连续失败"这么多次就停下。这是防止"接口整体挂了、代码还在傻跑"——
# 上面那次 500 部被误标失败，就是因为没有这道闸。
MAX_CONSEC_FAIL = 8

# 同一个条目（一部电影 / 一位影人）最多失败几次就不再自动重试。
# 抓失败不会把条目标成"已完成"，所以下次运行还会重试它，最多重试到这个次数为止。
# 想让它们立刻重试：`python crawl.py retry`
MAX_FAIL_PER_ITEM = 3

# 发现阶段：每个查询最多翻多少页（每页 20 条）
MAX_PAGES_PER_QUERY = 12

# 全局请求预算（防止一次跑太多；0 表示不限制）
MAX_REQUESTS_PER_RUN = 0

# ---------------------------------------------------------------- 请求头
UA_PC = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

UA_MOBILE = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
]

# ---------------------------------------------------------------- 接口地址
URL_HOME = "https://movie.douban.com/"
URL_SEARCH_API = "https://movie.douban.com/j/new_search_subjects"
URL_PC_SUBJECT = "https://movie.douban.com/subject/{id}/"
URL_PC_CELEBRITY = "https://movie.douban.com/celebrity/{id}/"
URL_REXXAR_MOVIE = "https://m.douban.com/rexxar/api/v2/movie/{id}?for_mobile=1"
URL_REXXAR_CELEBS = "https://m.douban.com/rexxar/api/v2/movie/{id}/celebrities?for_mobile=1"
URL_REXXAR_INTERESTS = ("https://m.douban.com/rexxar/api/v2/movie/{id}/interests"
                        "?count={count}&start={start}&type=comment&for_mobile=1")
URL_M_CELEBRITY = "https://m.douban.com/movie/celebrity/{id}/"
URL_SEC_SUBMIT = "https://sec.douban.com/c"

# ---------------------------------------------------------------- 发现阶段查询矩阵
# 豆瓣电影分类接口支持的参数：sort / range(评分区间) / tags / genres(类型) /
# countries(地区) / year_range(年份区间) / start(偏移)
GENRES = ["剧情", "喜剧", "动作", "爱情", "科幻", "动画", "悬疑", "惊悚", "恐怖",
          "纪录片", "短片", "音乐", "歌舞", "家庭", "儿童", "传记", "历史",
          "战争", "犯罪", "西部", "奇幻", "冒险", "灾难", "武侠", "古装",
          "运动", "黑色电影", "情色"]

# 评分区间（min,max）—— 用不同的评分带把同一批电影切散，避免翻页翻不深
RATING_BANDS = ["9,10", "8,9", "7,8", "6,7", "5,6", "0,5"]

# 年份区间 —— 同上，用来把结果集切小，让每个查询的翻页都能翻到底
YEAR_BANDS = ["2020,2026", "2015,2019", "2010,2014", "2000,2009",
              "1990,1999", "1980,1989", "1950,1979"]

# 地区（第二轮补充查询用）
COUNTRIES = ["中国大陆", "美国", "日本", "韩国", "中国香港", "中国台湾",
             "英国", "法国", "印度", "德国"]

# 排序方式：T=热度 S=评分 U=上映时间 R=看过人数
SORTS = ["T", "S", "U", "R"]
