/* ==========================================================================
   charts.js —— 每一张图长什么样，全在这个文件里
   --------------------------------------------------------------------------
   结构说明（改图的顺序就是照这个顺序找）：
     0. 公共样式 FX / AXIS / TIP   —— 所有图共用的颜色、坐标轴、提示框样式
     1. draw(id, option)           —— 把一段配置画到 index.html 里同名的容器上
     2. buildXxx() 一组函数        —— 每张图一个函数，函数名对应“图的中文名”
     3. initAllCharts()            —— 一次把所有图都画出来（被 js/main.js 调用）

   想改某张图：只改它对应的 buildXxx() 函数里的 option，比如
     · 想换成柱状图：把 option 里的 type: 'line' 改成 type: 'bar'
     · 想改颜色：改 color 数组，或用 FX.cyan 这类变量
     · 想改显示条数：改函数里 .slice(0, 10) 的 10
   ========================================================================== */

/* ---------- 0. 公共样式 ---------- */
const FX = {
  cyan: '#00e6ff',            // 主色
  blue: '#3f7bff',            // 副色
  purple: '#9d6bff',
  gold: '#ffc44d',
  green: '#3ddc97',
  dim: '#7fa6c8',             // 次要文字色
  axis: 'rgba(0,214,255,.35)' // 坐标轴颜色
};

// 类目轴 / 数值轴的公用配置（每个图里用 ...AXIS 展开复用）
const AXIS = {
  axisLine: { lineStyle: { color: FX.axis } },
  axisTick: { show: false },
  axisLabel: { color: FX.dim, fontSize: 11 },
  splitLine: { lineStyle: { color: 'rgba(0,214,255,.12)' } }
};

// 提示框（鼠标移上去的小浮窗）公用样式
const TIP = {
  backgroundColor: 'rgba(6,20,40,.92)',
  borderColor: FX.axis,
  textStyle: { color: '#e8f4ff', fontSize: 12 }
};

// 图表文字通用字体设置
const FONT = { fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif' };

const CHARTS = {};                       // id -> 图表实例（窗口变化时统一 resize；切换筛选时复用同一实例）

/* 1. 把一个 option 画到 id 对应的容器里。
   同一个 id 第二次调用会**复用实例并彻底重画**（setOption 第二个参数 true = notMerge），
   顶部筛选按钮切换时就靠这一点刷新，不会重复创建 canvas。 */
function draw(id, option) {
  const el = document.getElementById(id);
  if (!el) return null;                  // 容器不存在就跳过，避免报错
  let chart = CHARTS[id];
  if (!chart) { chart = echarts.init(el); CHARTS[id] = chart; }
  chart.setOption(option, true);
  return chart;
}

const D = window.DASH_DATA;              // 数据（来自 js/data.js）
const TOP = 10;                          // 排行榜类图表显示多少条，改这里即可

/* ---------- 筛选状态：顶部 chips 改的就是这一个对象 ---------- */
const STATE = { caliber: 'all', decade: 'all' };   // caliber: all/movie/tv；decade: all/1980s/2010s/2020s

/* 按当前筛选取一份数据。cross 的键是「口径|年代」，例如 "movie|2010s"。 */
function pick() {
  const f = D.filters;
  if (!f || !f.cross) {                              // 老版 data.js 没有 filters 时兜底
    return { genreTop: D.genreTop, countryTop: D.countryTop, topMovies: D.topMovies, n: D.kpi.works };
  }
  const cell = f.cross[STATE.caliber + '|' + STATE.decade] || {};
  return {
    genreTop: cell.genreTop || [],
    countryTop: cell.countryTop || [],
    topMovies: cell.topMovies || [],
    n: cell.n || 0
  };
}

/* 哪些图会跟着筛选变 —— main.js 里点完 chips 调一次这个函数就够了 */
function refreshFiltered() {
  buildGenre();
  buildDecade();
  buildCountry();
  buildRankTable();
}

/* ---------- 图 1：类型 TOP10（横向柱状图） ---------- */
function buildGenre() {
  const rows = pick().genreTop.slice(0, TOP).reverse();   // reverse：让第一名显示在最上面
  draw('chartGenre', {
    ...FONT,
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 40, top: 8, bottom: 4 },
    xAxis: { type: 'value', ...AXIS, axisLabel: { show: false }, splitLine: { show: false } },
    yAxis: { type: 'category', data: rows.map(r => r.name), ...AXIS, splitLine: { show: false } },
    series: [{
      type: 'bar',
      data: rows.map(r => r.value),
      barWidth: 12,
      itemStyle: {
        borderRadius: 6,
        // 每根柱子从青色渐变到蓝色
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: FX.blue }, { offset: 1, color: FX.cyan }])
      },
      label: { show: true, position: 'right', color: FX.cyan, fontSize: 11 }
    }]
  });
}

/* ---------- 图 2：年代分布（柱=作品数，线=平均分，双 Y 轴） ---------- */
/* 只受「口径」影响：按年代筛年代分布没有意义，所以这里不看 STATE.decade。 */
function buildDecade() {
  const f = D.filters;
  const dec = (f && f.byCaliber && f.byCaliber[STATE.caliber] && f.byCaliber[STATE.caliber].decade) || D.decade;
  draw('chartDecade', {
    ...FONT,
    tooltip: { ...TIP, trigger: 'axis' },
    legend: { data: ['作品数', '平均分'], textStyle: { color: FX.dim, fontSize: 11 }, right: 0, top: 0 },
    grid: { left: 40, right: 42, top: 26, bottom: 24 },   // bottom 要留够，不然 X 轴文字被切掉
    xAxis: { type: 'category', data: dec.labels, ...AXIS, splitLine: { show: false } },
    // 左轴：作品数量
    yAxis: [
      { type: 'value', ...AXIS, name: '部', nameTextStyle: { color: FX.dim, fontSize: 10 } },
      // 右轴：平均分（不显示网格线，避免和左轴重叠）
      { type: 'value', ...AXIS, min: 6, max: 10, splitLine: { show: false } }
    ],
    series: [
      { name: '作品数', type: 'bar', data: dec.counts, barWidth: 16,
        itemStyle: { color: 'rgba(63,123,255,.55)', borderRadius: [4, 4, 0, 0] } },
      { name: '平均分', type: 'line', yAxisIndex: 1, data: dec.avg, smooth: true,
        symbolSize: 6, lineStyle: { color: FX.gold, width: 2 }, itemStyle: { color: FX.gold } }
    ]
  });
}

/* ---------- 图 3：短评星级构成（环形图） ---------- */
function buildStar() {
  draw('chartStar', {
    ...FONT,
    tooltip: { ...TIP, trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, textStyle: { color: FX.dim, fontSize: 11 }, itemWidth: 10, itemHeight: 8 },
    color: [FX.cyan, FX.blue, FX.purple, FX.gold, '#ff7a7a', '#4a5a72'],
    series: [{
      type: 'pie',
      radius: ['42%', '68%'],                  // 内径/外径 → 环形
      center: ['50%', '45%'],
      data: D.starDist,
      label: { color: '#e8f4ff', fontSize: 11, formatter: '{b}\n{d}%' },
      labelLine: { length: 8, length2: 8, smooth: true },
      // 关键：扇区角度小于 6° 的不画标签。
      // 1星/2星/未评分 只占 0.6%~1.7%，硬画标签必然和邻居叠在一起；
      // 它们的数量在下方图例和鼠标提示里都能看到，不会丢信息。
      minShowLabelAngle: 6,
      avoidLabelOverlap: true,
      labelLayout: { hideOverlap: true }
    }]
  });
}

/* ---------- 图 4：中国地图（短评用户 IP 归属地） ---------- */
function buildMap() {
  echarts.registerMap('china', window.CHINA_GEOJSON);   // 注册地图轮廓
  draw('chartMap', {
    ...FONT,
    tooltip: { ...TIP, formatter: p => p.name + '：' + (p.value || 0) + ' 条短评' },
    // 左下角的颜色标尺：颜色越亮代表短评越多（calculable:false → 不要那个拖动的白色滑块）
    visualMap: {
      min: 0, max: D.mapMax, left: 16, bottom: 24, calculable: false,
      itemWidth: 10, itemHeight: 80,
      inRange: { color: ['#0b2a4a', '#12659b', '#00b3d6', '#00e6ff'] },
      textStyle: { color: FX.dim, fontSize: 11 }
    },
    series: [{
      type: 'map', map: 'china', roam: false,
      label: { show: true, color: 'rgba(232,244,255,.65)', fontSize: 9 },
      itemStyle: { borderColor: 'rgba(0,214,255,.45)', borderWidth: 1, areaColor: '#0b2a4a' },
      emphasis: { label: { color: '#fff' }, itemStyle: { areaColor: FX.blue } },
      data: D.mapData
    }]
  });
}

/* ---------- 图 5：评分 × 评价人数（散点图，纵轴取对数） ---------- */
function buildScatter() {
  draw('chartScatter', {
    ...FONT,
    tooltip: {
      ...TIP, trigger: 'item',
      formatter: p => p.data[2] + '<br/>评分 ' + p.data[0] + ' ／ 评价人数 ' + p.data[1].toLocaleString()
    },
    grid: { left: 68, right: 16, top: 12, bottom: 26 },
    xAxis: { type: 'value', min: 6, max: 10, name: '评分', nameTextStyle: { color: FX.dim, fontSize: 10 }, ...AXIS },
    // type:'log' → 评价人数从几万到几百万，用对数轴才不会挤成一团
    yAxis: {
      type: 'log', name: '评价人数', nameTextStyle: { color: FX.dim, fontSize: 10 }, ...AXIS,
      // 纵轴数字太长会顶出左边：1 万以上改写成“万”
      axisLabel: { color: FX.dim, fontSize: 10, formatter: v => (v >= 10000 ? (v / 10000) + '万' : v) }
    },
    series: [{
      type: 'scatter',
      data: D.scatter,
      symbolSize: 7,
      itemStyle: {
        color: FX.cyan, opacity: .6,
        shadowBlur: 8, shadowColor: 'rgba(0,214,255,.6)'
      }
    }]
  });
}

/* ---------- 图 6：制片国家 / 地区 TOP10 ---------- */
function buildCountry() {
  const rows = pick().countryTop.slice(0, TOP).reverse();
  draw('chartCountry', {
    ...FONT,
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 74, right: 40, top: 8, bottom: 4 },
    xAxis: { type: 'value', ...AXIS, axisLabel: { show: false }, splitLine: { show: false } },
    yAxis: { type: 'category', data: rows.map(r => r.name), ...AXIS, splitLine: { show: false } },
    series: [{
      type: 'bar', data: rows.map(r => r.value), barWidth: 12,
      itemStyle: {
        borderRadius: 6,
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: FX.purple }, { offset: 1, color: FX.cyan }])
      },
      label: { show: true, position: 'right', color: FX.cyan, fontSize: 11 }
    }]
  });
}

/* ---------- 图 7：高分榜 TOP10（排名表，不是 ECharts 图） ---------- */
/* 参考 awwwards 上 Field Rank 的榜单排版：大号名次 + 片名 + 右对齐的小数字。
   表格用 HTML 画（比 canvas 里的文字更清晰、也能用鼠标选中），
   所以这里不调用 draw()，而是把 HTML 填进 index.html 的 #rankTop。 */
function buildRankTable() {
  const box = document.getElementById('rankTop');
  if (!box) return;
  const rows = pick().topMovies;

  if (!rows.length) {                       // 某些筛选组合（如"剧集 + 1980s"）可能没有作品
    box.innerHTML = '<div class="rank-empty">该筛选下没有作品</div>';
    return;
  }

  box.innerHTML = rows.map(function (m, i) {
    const no = i + 1 < 10 ? '0' + (i + 1) : String(i + 1);
    const votes = m.votes >= 10000 ? (m.votes / 10000).toFixed(1) + '万' : m.votes.toLocaleString();
    return '<div class="rank-row" title="' + (m.year || '') + ' · ' + (m.genres || '') + '">' +
      '<span class="rk">' + no + '</span>' +
      '<span class="rk-name">' + m.name + '</span>' +
      '<span class="rk-year">' + (m.year || '') + '</span>' +
      '<span class="rk-score">' + m.rating.toFixed(1) + '</span>' +
      '<span class="rk-votes">' + votes + '</span>' +
      '</div>';
  }).join('');
}

/* ---------- 图 8：短评高频词（词云，需要 echarts-wordcloud 插件） ---------- */
function buildWord() {
  draw('chartWord', {
    ...FONT,
    tooltip: { ...TIP, formatter: p => p.name + '：出现 ' + p.value + ' 次' },
    series: [{
      type: 'wordCloud',
      shape: 'circle',                 // 词云外形：circle / cardioid / diamond / star...
      width: '100%', height: '100%',
      sizeRange: [10, 34],             // 字的最小/最大字号
      rotationRange: [0, 0],           // 0 = 不旋转（中文竖排不好看）
      gridSize: 6,                     // 词与词的间距
      textStyle: { color: () => ['#00e6ff', '#3f7bff', '#9d6bff', '#3ddc97', '#ffc44d'][Math.floor(Math.random() * 5)] },
      data: D.wordCloud
    }]
  });
}

/* ---------- 图 9：短评数量随年份变化（折线+渐变面积） ---------- */
function buildYear() {
  draw('chartYear', {
    ...FONT,
    tooltip: { ...TIP, trigger: 'axis' },
    grid: { left: 48, right: 20, top: 14, bottom: 20 },
    xAxis: { type: 'category', data: D.yearTrend.labels, ...AXIS, splitLine: { show: false } },
    yAxis: { type: 'value', ...AXIS },
    series: [{
      type: 'line', data: D.yearTrend.values, smooth: true, symbol: 'none',
      lineStyle: { color: FX.cyan, width: 2 },
      // 折线下方的渐变填充（青色由深到透明）
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0,230,255,.55)' }, { offset: 1, color: 'rgba(0,230,255,0)' }])
      }
    }]
  });
}

/* ---------- 一次画完全部（顺序无所谓，只是方便你对照着找） ---------- */
function initAllCharts() {
  buildGenre();
  buildDecade();
  buildStar();
  buildMap();
  buildScatter();
  buildCountry();
  buildRankTable();
  buildWord();
  buildYear();
}
