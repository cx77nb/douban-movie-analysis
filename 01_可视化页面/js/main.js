/* ==========================================================================
   main.js —— 「导航 + 切换 + 填文字」脚本（图表本身在 js/charts.js）
   --------------------------------------------------------------------------
   它干五件事：
     1. fitStage()      把 1920×1080 的舞台等比缩放到当前窗口（大屏不变形）
     2. buildNav()      生成顶部 01~06 导航按钮
     3. switchView(n)   切换整屏：隐藏其它 <section class="view">，显示第 n 屏
     4. fillXxx()       把 data.js 里的数字 / 文字 / 短评填进各屏的 HTML
     5. buildView(n)    第一次进入某屏时才画它的图（省启动时间）

   想加一屏的完整步骤（共 4 处）：
     a. index.html 里加 <section class="view" id="view-xxx">…</section>
     b. 下面 NAV 数组里加一条 { key:'xxx', num:'07', txt:'标题' }
     c. charts.js 里写 buildXxx() 画图
     d. 下面的 RENDER 表里加一行 xxx: [buildXxx, ...]
   ========================================================================== */

/* ---------------- 舞台等比缩放 ---------------- */
function fitStage() {
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  const stage = document.getElementById('stage');
  stage.style.transform = `scale(${s})`;
  // 缩放后左上角对齐、水平居中
  stage.style.left = (window.innerWidth - 1920 * s) / 2 + 'px';
}

/* ---------------- 导航定义（想改名字就改这里） ---------------- */
const NAV = [
  { key: 'overview', num: '01', txt: '概览' },
  { key: 'genre',    num: '02', txt: '类型与年代' },
  { key: 'country',  num: '03', txt: '国家与地区' },
  { key: 'comment',  num: '04', txt: '短评' },
  { key: 'model',    num: '05', txt: '建模' },
  { key: 'rank',     num: '06', txt: '榜单' }
];

/* 每屏第一次进入时要画哪些图（函数名来自 charts.js） */
const RENDER = {
  overview: [buildWorld],
  genre:    [buildGenre, buildDecade, buildScatter, buildYear],
  country:  [buildCountry],
  comment:  [buildWord, buildStarDual],
  model:    [buildModelBar, buildConfusion],
  rank:     []
};

const drawnOnce = {};   // 记录哪些屏已经画过，避免重复 init
let currentKey = null;

function buildNav() {
  const bar = document.getElementById('navBar');
  bar.innerHTML = '';
  NAV.forEach(item => {
    const el = document.createElement('div');
    el.className = 'nav-item';
    el.dataset.key = item.key;
    // 编号与文字分成两层，方便 CSS 分别控制字号/字距
    const num = document.createElement('span');
    num.className = 'num';
    num.textContent = item.num;
    const txt = document.createElement('span');
    txt.className = 'txt';
    txt.textContent = item.txt;
    el.appendChild(num);
    el.appendChild(txt);
    el.addEventListener('click', () => switchView(item.key));
    bar.appendChild(el);
  });
}

/* 切换整屏：所有 .view 先关掉，再把目标屏打开（CSS 里有 200ms 淡入） */
function switchView(key) {
  currentKey = key;

  document.querySelectorAll('.view').forEach(v => {
    const on = v.id === 'view-' + key;
    v.classList.toggle('on', on);
    // 用内联样式直接写显隐：CSS 里的 .view.on 规则要靠过渡类收尾，
    // 内联最直接，也不受 transition 影响。
    v.style.visibility = on ? 'visible' : 'hidden';
    v.style.opacity = on ? '1' : '0';
  });
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('on', el.dataset.key === key);
  });

  // 画图放在下一帧：先让浏览器把显隐 / 尺寸算完，再画。
  // 用 setTimeout 而不是 requestAnimationFrame：无头浏览器 / 后台标签页里
  // rAF 可能被完全挂起（页面不动它就不给回调）。
  setTimeout(() => renderView(key), 32);
}

/* 画某一屏的图 + 词云体检。
   单独抽成函数，是为了让启动时「先画当前屏、再后台预画其余屏」能复用。 */
function renderView(key) {
  const fns = RENDER[key] || [];
  if (!drawnOnce[key]) {
    fns.forEach(fn => fn());
    drawnOnce[key] = true;
  }
  Object.values(CHARTS).forEach(c => c.resize());
}

/* ======================= ① 概览：数据带 ======================= */
/* 一条「数字 + 小方块」：1052 个小方块代表 1052 部作品，
   每满 100 个把方块染成强调色，方便一眼数出百位。 */
function buildScale() {
  const box = document.getElementById('scaleBar');
  const s = D.scale;
  // 约简写法：大数字 + 标签
  const fmt = n => (n >= 10000 ? (n / 10000).toFixed(n >= 100000 ? 0 : 1) + ' 万' : n);
  const nums = [
    [s.works, '部影视作品'],
    [s.comments, '条热门短评'],
    [s.genres, '种类型'],
    [s.countries, '个国家 / 地区'],
    [s.years + ' 年', '年份跨度'],
    [fmt(s.votes_sum), '人次评价']
  ];
  box.innerHTML = '';
  nums.forEach(([v, l]) => {
    const d = document.createElement('div');
    d.className = 'num-block';
    d.innerHTML = `<div class="v tnum">${v}</div><div class="l">${l}</div>`;
    box.appendChild(d);
  });

  // 1052 个方块：一个方块 = 一部作品，每 100 部标一个橙点（方便数到千）。
  // 用 CSS Grid 一次排好，不逐个 appendChild（那样会慢）。
  const gridWrap = document.createElement('div');
  gridWrap.className = 'grid-wrap';
  const grid = document.createElement('div');
  grid.className = 'block-grid';
  let html = '';
  for (let i = 0; i < s.works; i++) {
    html += (i % 100 === 0 ? '<i class="mark"></i>' : '<i></i>');
  }
  grid.innerHTML = html;
  // 图下方一行说明：不讲清楚读者不知道这一片方块是什么
  const cap = document.createElement('div');
  cap.className = 'grid-cap';
  cap.innerHTML =
    `<b>每格 1 部</b>　共 <b>${s.works}</b> 部　` +
    `<i class="dot"></i>橙点 = 每满 100 部的刻度`;
  gridWrap.appendChild(grid);
  gridWrap.appendChild(cap);
  box.appendChild(gridWrap);
}

/* ======================= ① 概览：地图图例 ======================= */
/* 让「未收录」这件事自己说清楚：灰色 = 本数据集没抓到该国的作品，
   不是数据出错，而是采样范围只覆盖到 43 个国家/地区。
   色块颜色必须和 charts.js 的 WORLD_STOPS 一致。 */
function fillMapLegend() {
  const box = document.getElementById('mapLegend');
  if (!box) return;
  const w = D.world || {};
  const items = [
    ['#332723', '1–2'],
    ['#833f32', '3–15'],
    ['#b44d37', '16–60'],
    ['#ff8a63', '60+'],
    ['#1b2129', '未收录', true]
  ];
  box.innerHTML =
    `<div class="lg-row">${items.map(([c, t, none]) =>
      `<span class="lg"><i${none ? ' class="none"' : ''} style="${none ? '' : 'background:' + c}"></i>${t}</span>`
    ).join('')}<span class="lg-unit">部作品</span></div>`
    + `<div class="lg-tip">灰色 = 本数据集在这 ${w.n_countries || 43} 个国家/地区之外，不是数据出错</div>`;
}

/* ======================= ① 概览：反直觉结论 + 37% 环 ======================= */
function fillFinding() {
  const b = D.banner;
  const R = 46, C = 2 * Math.PI * R;         // 半径 / 周长
  const pct = b.hot_pct;
  const dash = C * pct / 100;
  document.getElementById('finding').innerHTML = `
    <div class="ring">
      <svg width="118" height="118" viewBox="0 0 118 118">
        <circle cx="59" cy="59" r="${R}" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="7"/>
        <circle cx="59" cy="59" r="${R}" fill="none" stroke="#ff6b4a" stroke-width="7"
                stroke-linecap="round"
                stroke-dasharray="${dash} ${C - dash}"/>
      </svg>
      <div class="val tnum">${pct}%</div>
    </div>
    <div class="txt">
      <div class="big">有 <em>${b.hot}</em> 部作品评分在 9 分以上，<br/>却连十万人都没评价过。</div>
      <div class="sub">全库 ${b.rating9} 部 9 分以上作品中占 ${pct}%。高分不等于大众，豆瓣高分片里有相当一部分是小众佳作。</div>
    </div>`;
}

/* ======================= ① 概览：三条结论 ======================= */
function fillNotes() {
  const b = D.banner;
  const s = D.scale;
  const rows = [
    ['题材', `「${b.genre_top}」以 <b>${b.genre_top_n}</b> 部位居第一，占全库 ${(b.genre_top_n / s.works * 100).toFixed(0)}%`],
    ['年代', `<b>${b.decade_top}</b> 最多（<b>${b.decade_top_n}</b> 部），1950s 起每个十年都有收录`],
    ['口碑', `短评中五星占 <b>${b.avg_five}%</b>，四星以上合计 <b>${b.avg_good}%</b>`]
  ];
  document.getElementById('overviewNotes').innerHTML = rows.map(([k, v]) =>
    `<div class="note-row"><span class="k">${k}</span><span class="v">${v}</span></div>`
  ).join('');
}

/* ======================= ③ 国家：43 国明细 ======================= */
/* 两列可滚动列表，条长按最大值等比缩放。
   注意：两栏是「上下排满左栏再排右栏」不行，grid 默认是先行后列，
   所以这里用 grid-auto-flow: column 在 CSS 里控制（见 .country-list）。 */
function fillCountryList() {
  const rows = D.world.data.slice().sort((a, b) => b.value - a.value);
  const max = rows.length ? rows[0].value : 1;
  document.getElementById('countryList').innerHTML = rows.map((r, i) => {
    const w = Math.max(3, Math.round(r.value / max * 78));
    return `<div class="cl-row">
      <span class="nm">${r.cn}</span>
      <span class="bar${i < 3 ? ' hot' : ''}" style="width:${w}px"></span>
      <span class="n tnum">${r.value}</span>
    </div>`;
  }).join('');
  // 标题上的「45 个」跟随真实数据，别写死
  const h = document.querySelector('#view-country .card:last-child h3');
  if (h) h.childNodes.forEach(n => {
    if (n.nodeType === 3 && n.textContent.indexOf('个') > 0) {
      n.textContent = n.textContent.replace(/\d+ 个/, rows.length + ' 个');
    }
  });
}

/* ======================= ④ 短评：真实示例 ======================= */
/* 星级用「★」写出来；四星以上用强调色，让人一眼看出情绪分层 */
function fillSamples() {
  const stars = n => (n ? '★'.repeat(n) + '☆'.repeat(5 - n) : '未评');
  /* ★ 为什么写成 <i> + <span class="st-no"> 两层：
       .sample 是行等高的 flex，如果让「★★★★★」这段文本直接占一格，
       它的字形高度会撑高整行、把正文挤歪（CSS 里 .st-line 用 font-size:0
       把这个纯文本节点的高度归零，只剩 <i> 决定高度）。
       星级只上色，不参与尺寸。 */
  document.getElementById('samples').innerHTML = D.samples.map(s => `
    <div class="sample">
      <span class="st">
        <span class="st-line"><i class="${s.star >= 4 ? 'hi' : ''}">${stars(s.star)}</i></span>
        <span class="st-no tnum">${s.star ? s.star + ' 星' : '未评'}</span>
      </span>
      <span class="tx"><b>《${s.movie}》</b>　${s.text}</span>
    </div>`).join('');
}

/* ======================= ⑤ 建模：结论 + 特征词 ======================= */
function fillModelVerdict() {
  const m = D.model;
  document.getElementById('modelVerdict').innerHTML =
    `用 ${m.n} 条有效短评做 5 折交叉验证，<b>AUC ${m.auc.toFixed(3)}</b>、准确率 ${(m.acc * 100).toFixed(1)}%。` +
    `作为对照：完全瞎猜是 0.500，只猜多数类是 ${m.baseline.toFixed(3)}，` +
    `「看一眼同一部片其他短评投多数票」是 ${m.same_movie.toFixed(3)}。`;
}

function fillWords() {
  const m = D.model;
  // 正负词各取前 12 个；去重（"五星" 出现过两次）
  const uniq = a => [...new Set(a)].slice(0, 12);
  /* 为什么要包一层 .wtags：.ws 是 flex 换行容器，
     词条按内容宽度排列，最后一行会参差不齐、底部留白。
     包成 grid（每行 3 格、格子等宽等高）后整块正好铺满，
     字号也能调大，短词长词看起来一样齐。 */
  const tags = (arr, cls) => `<div class="ws"><div class="wtags">${
    uniq(arr).map(w => `<span class="wtag ${cls}">${w}</span>`).join('')
  }</div></div>`;
  document.getElementById('wordsDuo').innerHTML = `
    <div class="words-col">
      <span class="cap">推动「给五星」的词</span>
      ${tags(m.pos_words, 'pos')}
    </div>
    <div class="words-col">
      <span class="cap">推动「不给满分」的词</span>
      ${tags(m.neg_words, 'neg')}
    </div>
    <div class="words-col">
      <span class="cap">一句话读法</span>
      <div class="ws" style="font-size:13.5px;line-height:1.75;color:#9aa1a8;display:block">
        好评靠<b style="color:#ff6b4a">情绪爆发</b>（感叹号、童年、温暖），
        差评靠<b style="color:#8fa6b8">礼貌转折</b>（「，但」「其实」「有点」），
        而不是脏话 —— 中文差评是「欲扬先抑」的。
      </div>
    </div>`;
}

/* ======================= ⑥ 榜单 ======================= */
/* 一张榜 = 若干行。五列：名次 / 片名 / 年份 / 评分 / 评价人数 */
function rankRows(list, startNo) {
  return list.map((m, i) => `
    <div class="rk-row">
      <span class="rk tnum">${startNo + i}</span>
      <span class="nm">${m.name}</span>
      <span class="yr tnum">${m.year || ''}</span>
      <span class="sc tnum">${m.rating}</span>
      <span class="vt tnum">${m.votes >= 10000 ? (m.votes / 10000).toFixed(1) + '万' : m.votes}</span>
    </div>`).join('');
}

function fillRank() {
  // 左：书架里评上「豆瓣 Top250」的那批（data.js 新增的 top250 键，只含 is_top250=1 的作品）
  // 万一导出脚本没生成这个键，退回用全库高分榜，保证页面不空
  const top = (D.top250 && D.top250.length) ? D.top250 : D.topMovies;
  document.getElementById('rankList').innerHTML = rankRows(top.slice(0, 18), 1);
  document.getElementById('rankNote').textContent = `共 ${D.kpi.top250} 部入选豆瓣 Top250`;

  // 右：全库高分榜（按评分降序，同名只留评价人数最多，取前 18）
  document.getElementById('rankAll').innerHTML = rankRows(D.topMovies.slice(0, 18), 1);
}

/* ======================= 启动 ======================= */
function boot() {
  fitStage();
  buildNav();
  buildScale();
  fillMapLegend();
  fillFinding();
  fillNotes();
  fillCountryList();
  fillSamples();
  fillModelVerdict();
  fillWords();
  fillRank();

  // 底部信息
  document.getElementById('footLeft').textContent =
    `数据采集于 ${D.updated} · 豆瓣电影公开页面 · 免登录`;
  document.getElementById('footRight').textContent =
    `共 ${D.kpi.works} 部作品 / ${D.kpi.comments} 条短评 · 离线渲染 · ECharts 5.5.1`;

  switchView('overview');

  // 启动后把其余几屏的图也悄悄画好（此时它们是 visibility:hidden，但
  // 容器仍有真实宽高，能正确量尺寸）。这样第一次点开是立刻出现、不闪白。
  setTimeout(() => {
    NAV.forEach((item, i) => {
      if (item.key === 'overview') return;
      setTimeout(() => { if (!drawnOnce[item.key]) { renderView(item.key); } }, i * 120);
    });
  }, 600);
}

window.addEventListener('resize', fitStage);
boot();
