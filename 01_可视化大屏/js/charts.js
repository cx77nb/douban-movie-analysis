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
     · 想改颜色：改 color 数组，或用 FX.accent / FX.bar 这类变量
     · 想改显示条数：改函数里 .slice(0, 10) 的 10
   ========================================================================== */

/* ---------- 0. 公共样式 ---------- */
/* 配色原则：中性灰打底，**只有一个强调色**。
   想换主题色，只改 FX.accent 一行（CSS 里的 --accent 也一起改）。 */
const FX = {
  accent: '#e8b95f',                  // 唯一的彩色：铜金
  text: '#eceff2',                    // 主文字（不用纯白）
  dim: '#8b9299',                     // 次要文字 / 坐标轴
  mute: '#5c636b',                    // 最弱：单位、编号
  line: 'rgba(255,255,255,.07)',      // 结构线
  bar: 'rgba(255,255,255,.20)',       // 普通柱子：中性灰
  barDim: 'rgba(255,255,255,.13)'     // 更弱的柱子（背景层）
};

// 类目轴 / 数值轴的公用配置（每个图里用 ...AXIS 展开复用）
const AXIS = {
  axisLine: { lineStyle: { color: FX.line } },
  axisTick: { show: false },
  axisLabel: { color: FX.dim, fontSize: 10 },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,.05)' } }
};

// 提示框（鼠标移上去的小浮窗）公用样式：深灰底 + 发丝边，不要发光
const TIP = {
  backgroundColor: 'rgba(14,17,20,.97)',
  borderColor: 'rgba(255,255,255,.12)',
  borderWidth: 1,
  padding: [8, 11],
  textStyle: { color: FX.text, fontSize: 12 },
  extraCssText: 'border-radius:3px;box-shadow:none;'
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
      barWidth: 10,
      // 只有第一名（reverse 后是最后一条）用铜金，其余全是中性灰 —— "只亮重点"
      itemStyle: {
        borderRadius: 1,
        color: p => (p.dataIndex === rows.length - 1 ? FX.accent : FX.bar)
      },
      label: {
        show: true, position: 'right', fontSize: 10,
        color: p => (p.dataIndex === rows.length - 1 ? FX.accent : FX.dim)
      }
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
      { name: '作品数', type: 'bar', data: dec.counts, barWidth: 14,
        itemStyle: { color: FX.barDim, borderRadius: 1 } },
      { name: '平均分', type: 'line', yAxisIndex: 1, data: dec.avg, smooth: true,
        symbolSize: 5, lineStyle: { color: FX.accent, width: 1.6 }, itemStyle: { color: FX.accent } }
    ]
  });
}

/* ---------- 图 3：短评星级构成（环形图） ---------- */
function buildStar() {
  draw('chartStar', {
    ...FONT,
    tooltip: { ...TIP, trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, textStyle: { color: FX.dim, fontSize: 10 }, itemWidth: 8, itemHeight: 8, itemGap: 14 },
    // 单色阶：5 星最亮（铜金），星级越低越暗，"未评分"用中性灰
    color: ['#e8b95f', '#c79a47', '#9e7935', '#755727', '#4a3a1d', '#2a2e33'],
    series: [{
      type: 'pie',
      radius: ['50%', '74%'],                  // 内径/外径 → 环形
      center: ['50%', '44%'],
      data: D.starDist,
      itemStyle: { borderColor: '#0e1114', borderWidth: 2 },   // 扇区之间留一条底色缝，更精致
      label: { color: FX.text, fontSize: 10.5, formatter: '{b} {d}%' },
      labelLine: { length: 10, length2: 8, smooth: true, lineStyle: { color: 'rgba(255,255,255,.18)' } },
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
    // 左下角的颜色标尺：越亮代表短评越多（深灰 → 铜金，不用青色）
    visualMap: {
      min: 0, max: D.mapMax, left: 14, bottom: 16, calculable: false,
      itemWidth: 8, itemHeight: 62, itemGap: 8,
      text: ['多', '少'],                   // 显式写出两端含义，默认的英文提示太小
      inRange: { color: ['#15191f', '#2f2517', '#5b4523', '#9c7534', '#e8b95f'] },
      textStyle: { color: FX.mute, fontSize: 9.5 }
    },
    series: [{
      type: 'map', map: 'china', roam: false,
      // 放大一点，别让地图缩在卡片中间一小块
      layoutCenter: ['53%', '53%'], layoutSize: '122%',
      /* ★ 省名默认不显示。1052 部作品的短评高度集中在东部，省市名字会全挤成一团，
         这是最容易显乱的地方；鼠标移上去（emphasis）才显示名字，
         而"哪里人多"这件事已经由颜色表达了。 */
      label: { show: false },
      itemStyle: { borderColor: 'rgba(255,255,255,.16)', borderWidth: 1, areaColor: '#161b21' },
      emphasis: { label: { show: true, color: '#fff', fontSize: 11 }, itemStyle: { areaColor: '#4a3b22' } },
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
    // 评分几乎全在 8~10 分，横轴从 6 开始会在左边留一大片空白，所以收紧到 7.8
    xAxis: { type: 'value', min: 7.8, max: 10, name: '评分', nameTextStyle: { color: FX.mute, fontSize: 9.5 }, ...AXIS },
    // type:'log' → 评价人数从几万到几百万，用对数轴才不会挤成一团
    yAxis: {
      type: 'log', name: '评价人数', nameTextStyle: { color: FX.dim, fontSize: 10 }, ...AXIS,
      // 纵轴数字太长会顶出左边：1 万以上改写成“万”
      axisLabel: { color: FX.dim, fontSize: 10, formatter: v => (v >= 10000 ? (v / 10000) + '万' : v) }
    },
    series: [{
      type: 'scatter',
      data: D.scatter,
      symbolSize: 5,
      itemStyle: {
        color: FX.accent, opacity: .55         // 半透明小点，密集处自然叠出层次；不加发光
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
      type: 'bar', data: rows.map(r => r.value), barWidth: 10,
      // 同样只高亮第一名
      itemStyle: {
        borderRadius: 1,
        color: p => (p.dataIndex === rows.length - 1 ? FX.accent : FX.bar)
      },
      label: {
        show: true, position: 'right', fontSize: 10,
        color: p => (p.dataIndex === rows.length - 1 ? FX.accent : FX.dim)
      }
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
  // 先算最大词频，用它做"高/中/低"三档配色的分界（自适应，不写死阈值）
  const wmax = Math.max.apply(null, D.wordCloud.map(function (d) { return d.value; }).concat([1]));
  draw('chartWord', {
    ...FONT,
    tooltip: { ...TIP, formatter: p => p.name + '：出现 ' + p.value + ' 次' },
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      width: '100%', height: '100%',
      sizeRange: [11, 36],
      rotationRange: [0, 0],
      gridSize: 6,
      /* 颜色**不要用 Math.random()**：那会让每次刷新颜色都变，看着很廉价。
         这里按词频固定分三档：高频铜金、中频浅灰、低频暗灰。 */
      textStyle: {
        fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif',
        color: p => (p.value >= wmax * 0.6 ? FX.accent
          : (p.value >= wmax * 0.22 ? '#cfd4d8' : FX.mute))
      },
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
      lineStyle: { color: FX.accent, width: 1.8 },
      // 折线下方的渐变填充（铜金由淡到透明）
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(232,185,95,.28)' }, { offset: 1, color: 'rgba(232,185,95,0)' }])
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
