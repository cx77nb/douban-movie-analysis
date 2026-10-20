/* ==========================================================================
   charts.js —— 所有 ECharts 图表的「配置」
   --------------------------------------------------------------------------
   分工：
     charts.js  只负责画图（每个 buildXxx() 画一块）
     main.js    负责导航、切换视图、把文字填进 HTML
   两者靠全局变量 D 通信（D = window.DASH_DATA，来自 js/data.js）。

   改颜色的唯一入口是下面的 FX。想整体换色 → 改 FX.accent 一处，
   再同步 css/style.css 里的 --hot。
   ========================================================================== */

const D = window.DASH_DATA;

/* FX = 调色板。所有图表都从这里取色，不要在下面对某个图单独写色值。 */
const FX = {
  accent: '#ff6b4a',               // 唯一强调色（珊瑚橘）
  text:   '#eef1f4',               // 主文字
  dim:    '#9aa1a8',               // 次要文字
  mute:   '#61686f',               // 弱化文字 / 网格线
  line:   'rgba(255,255,255,.07)',
  bar:    'rgba(255,255,255,.20)', // 普通柱子
  barDim: 'rgba(255,255,255,.09)'  // 更淡的一档
};

/* 字体：和 style.css 里 :root 的 --font-serif / --font-sans 是同一套名字，
   换字体时两边要一起改，名字写不一致图表文字就会和页面文字变成两种字体。
   2026-10-20：原来的宋体（SimSun）在近黑底上笔画发虚，改以思源黑体为主，
   只在需要"衬线感"的地方（FONT）用思源宋体。 */
const FSANS = '"Noto Sans SC","Microsoft YaHei","PingFang SC","Segoe UI",sans-serif';
const FONT = '"Noto Sans SC","Microsoft YaHei","PingFang SC",sans-serif';

/* CHARTS：图表实例表。resize 时要遍历它，所以是对象不是数组。
   注意：不能写 CHARTS.forEach —— 对象没有 forEach，会静默失效。 */
const CHARTS = {};

/* 地图用的英文国名 → 中文显示名。
   注意两个地方都要用它：series.nameMap（悬停显示中文）和 series.regions 的 name
   （区域着色）。因为 nameMap 会把底图区域名直接改成中文，regions 若还写英文就
   匹配不上，整幅地图会只剩一种颜色且不报错。 */
const NAME_MAP = {
  'United States': '美国', 'China': '中国（含港台）', 'United Kingdom': '英国',
  'Japan': '日本', 'Korea': '韩国', 'France': '法国', 'Italy': '意大利',
  'Germany': '德国', 'India': '印度', 'Canada': '加拿大', 'Spain': '西班牙',
  'Russia': '俄罗斯', 'Australia': '澳大利亚', 'Brazil': '巴西',
  'New Zealand': '新西兰', 'Sweden': '瑞典', 'Denmark': '丹麦',
  'Norway': '挪威', 'Finland': '芬兰', 'Poland': '波兰',
  'Netherlands': '荷兰', 'Belgium': '比利时', 'Switzerland': '瑞士',
  'Austria': '奥地利', 'Ireland': '爱尔兰', 'Mexico': '墨西哥',
  'Argentina': '阿根廷', 'Thailand': '泰国', 'Iran': '伊朗',
  'Turkey': '土耳其', 'Israel': '以色列', 'Czech Rep.': '捷克',
  'Czechia': '捷克', 'Hungary': '匈牙利', 'Romania': '罗马尼亚',
  'Bulgaria': '保加利亚', 'Greece': '希腊', 'Portugal': '葡萄牙',
  'Ukraine': '乌克兰', 'Vietnam': '越南', 'Singapore': '新加坡',
  'Malaysia': '马来西亚', 'Indonesia': '印度尼西亚', 'Philippines': '菲律宾',
  'Egypt': '埃及', 'South Africa': '南非', 'Chile': '智利',
  'Colombia': '哥伦比亚', 'Peru': '秘鲁', 'Cuba': '古巴',
  'Iceland': '冰岛', 'Luxembourg': '卢森堡', 'United Arab Emirates': '阿联酋',
  'Saudi Arabia': '沙特阿拉伯', 'Serbia': '塞尔维亚', 'Jordan': '约旦',
  'Lebanon': '黎巴嫩', 'Cyprus': '塞浦路斯', 'Qatar': '卡塔尔',
  'Belarus': '白俄罗斯', 'Latvia': '拉脱维亚', 'Morocco': '摩洛哥'
};

/* 在地图类图表画之前，必须先把 GeoJSON 注册给 ECharts。
   这里用「已注册就不重复注册」的写法，切屏多次也不会报错。 */
function ensureMaps() {
  if (!D || !window.WORLD_GEOJSON) return;
  if (!echarts.getMap('world')) echarts.registerMap('world', window.WORLD_GEOJSON);
}

/* draw(id, option)：按 id 复用实例（切屏回来不会重建、动画不重播） */
function draw(id, option) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!CHARTS[id]) CHARTS[id] = echarts.init(el, null, { renderer: 'canvas' });
  CHARTS[id].setOption(option, true);
}

/* 统一提示框样式，避免每个图重复写 */
const TIP = {
  backgroundColor: 'rgba(16,19,23,.96)',
  borderColor: 'rgba(255,255,255,.14)',
  borderWidth: 1,
  padding: [8, 11],
  textStyle: { color: FX.text, fontSize: 12, fontFamily: FONT }
};

/* 横向条形图的通用配置：labels 从左到右，值越大越靠上，
   且只把「第一名」染成强调色。 */
function hBar(labels, values, opts = {}) {
  const n = labels.length;
  /* 右侧留白按最大值的位数算。写死 46px 的话，数值从 "591" 变成 "374" 这种
     位数变化时标签会被挤出卡片；按位数算，10 行 / 15 行都不会被裁。 */
  const maxV = Math.max.apply(null, values.concat([1]));
  const gutter = 16 + String(maxV).length * 8;
  return {
    animationDuration: 500,
    // 行数少时留白会很难看：给 grid 留出上下余量，柱子按比例拉开，
    // 卡片再高也不会只剩顶部一条。opts.spread 为 true 时把行距撑满。
    grid: { left: 0, right: gutter, top: opts.spread ? 18 : 4, bottom: opts.spread ? 18 : 0, containLabel: true },
    // max 用来给条形图封顶：不做封顶的话，一个大数会把其他条全压成短棍
    xAxis: { type: 'value', show: false, max: opts.max },
    yAxis: {
      type: 'category',
      data: labels.slice().reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      // 类目多时字号要跟着缩小，否则 15 行会挤成一坨
      axisLabel: { color: FX.dim, fontSize: opts.labelSize || 13, fontFamily: FONT, margin: 10 }
    },
    tooltip: {
      ...TIP,
      trigger: 'axis',
      axisPointer: { type: 'none' },
      formatter: p => `${p[0].name}<br/><b style="color:${FX.accent}">${p[0].value}</b> ${opts.unit || '部'}`
    },
    series: [{
      type: 'bar',
      data: values.slice().reverse(),
      // 行数少（<8）时把柱子加粗，否则 15 厘米高的卡片里一条线一样细
      barWidth: opts.barWidth || (n <= 8 ? 16 : 9),
      itemStyle: {
        // 只给第一名（原数组最后一项）上强调色
        color: p => (p.dataIndex === n - 1 ? FX.accent : FX.bar),
        borderRadius: [0, 1, 1, 0]
      },
      label: {
        show: true, position: 'right', color: FX.mute,
        fontSize: 12, fontFamily: FSANS,
        formatter: p => p.value
      }
    }]
  };
}

/* ======================= 01 世界地图 ======================= */
/* 数据来自 data.js 的 world：43 个国家（英文 geo 名 + 中文别名 + 拆分来源）。
   没有收录的国家用深色底 #1b2129，有收录的按作品数插值成暖色。

   ★★ 为什么用 geo 组件而不是 map series（踩了很久的坑，别再改回去）
   ECharts 5.5.1 里 `series: [{ type: 'map' }]` 有以下行为：
     · 默认 colorBy='series'，visualMap 完全不参与区域着色；
     · 显式写 colorBy:'data' 后，getData().getVisual('color') 仍是 undefined；
     · data[].itemStyle.color 只进了 itemModel，绘制时被忽略；
     · series.regions 写英文名不生效，写中文名（nameMap 翻译后）也不生效。
   实测下来 map series 的 217 个区域永远统一取 itemStyle.areaColor，
   而 **geo 组件的 regions 完全正常**（测过：216 灰 + 1 红）。
   所以这里用 geo 承载地图和逐国颜色，map series 只放数据供 tooltip 用。 */

/* 43 个国家的经纬度中心点（[经度, 纬度]）。
   只用于给散点系列定位，让悬停提示能落到对应国家上。 */
const GEO_CENTER = {
  'United States': [-100, 40], 'China': [104, 35], 'United Kingdom': [-2.5, 54],
  'Japan': [138, 37], 'Korea': [127.8, 36.5], 'France': [2.5, 46.6],
  'Germany': [10.4, 51.1], 'Italy': [12.6, 42.8], 'Canada': [-100, 57],
  'Russia': [100, 60], 'India': [79, 22], 'Spain': [-3.7, 40.4],
  'Czech Rep.': [15.5, 49.8], 'Switzerland': [8.2, 46.8], 'Thailand': [101, 15.5],
  'New Zealand': [172, -41], 'Sweden': [15, 62], 'Poland': [19.4, 52.1],
  'Ireland': [-8, 53.2], 'Australia': [134, -25], 'Belgium': [4.5, 50.6],
  'Netherlands': [5.6, 52.2], 'Hungary': [19.5, 47.2], 'Brazil': [-51, -10],
  'Iran': [53, 32], 'Austria': [14.5, 47.6], 'Denmark': [9.5, 56],
  'Singapore': [103.8, 1.35], 'South Africa': [24, -29], 'Cuba': [-79.5, 21.5],
  'Serbia': [20.8, 44.2], 'Mexico': [-102, 23.6], 'Jordan': [36.5, 31.2],
  'Norway': [9, 61.5], 'Luxembourg': [6.1, 49.8], 'Argentina': [-64, -34],
  'Lebanon': [35.8, 33.9], 'Cyprus': [33.2, 35], 'Qatar': [51.2, 25.3],
  'Belarus': [28, 53.5], 'Latvia': [24.6, 56.9], 'Iceland': [-19, 65],
  'Morocco': [-6.5, 31.8]
};

/* 色阶：从「暗暖灰」到「亮珊瑚」，四段线性插值。
   ★ 分段阈值取 log10 而不是线性归一化：
   美国 374、中国 284，而 43 个国家里有 24 个只有 1~3 部作品。
   线性映射会让这 24 个全贴在色阶最底端、等于隐形；
   而 log 归一化又把差距压平（俄罗斯 18 部也吃到接近最亮的色）。
   所以按「部数档位」切：
     1~2 部  → t=0.00  极暗暖灰，只在图上"有个存在感"
     3~5 部  → t=0.22
     6~15 部 → t=0.40
     16~60部 → t=0.62
     60+ 部  → t=0.85 以上，越往上越亮
   这样"有收录"和"很多收录"能一眼分开，图中也不再到处是亮橙。 */
const WORLD_BANDS = [
  [2, 0.00],      // ≤2 部
  [5, 0.22],      // ≤5 部
  [15, 0.40],     // ≤15 部
  [60, 0.62],     // ≤60 部
  [160, 0.80],    // ≤160 部
  [Infinity, 1.00]
];

const WORLD_STOPS = [
  [0.00, [0x33, 0x27, 0x23]],   // 极暗暖灰（仍能看出"有收录"）
  [0.22, [0x5a, 0x32, 0x2b]],
  [0.40, [0x83, 0x3f, 0x32]],
  [0.62, [0xb4, 0x4d, 0x37]],
  [0.80, [0xdd, 0x67, 0x45]],
  [1.00, [0xff, 0x8a, 0x63]]    // 美国 374
];

/* 把「部数」映射成 0~1 的色阶位置 */
function worldT(v) {
  for (let i = 0; i < WORLD_BANDS.length; i++) {
    if (v <= WORLD_BANDS[i][0]) return WORLD_BANDS[i][1];
  }
  return 1;
}

/* 把 0~1 的数映射成颜色字符串 */
function worldColor(t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < WORLD_STOPS.length; i++) {
    const p1 = WORLD_STOPS[i][0];
    if (t <= p1) {
      const p0 = WORLD_STOPS[i - 1][0];
      const c0 = WORLD_STOPS[i - 1][1];
      const c1 = WORLD_STOPS[i][1];
      const k = (t - p0) / (p1 - p0 || 1);
      const ch = j => Math.round(c0[j] + (c1[j] - c0[j]) * k).toString(16).padStart(2, '0');
      return '#' + ch(0) + ch(1) + ch(2);
    }
  }
  return '#ff8a63';
}

function buildWorld() {
  ensureMaps();                       // 先注册地图轮廓，否则 echarts 会报 map not found
  const w = D.world;

  /* geo 的 regions 按「底图原名」匹配 —— 这里不写 nameMap，
     所以一律用 GeoJSON 里的英文名，不要翻译成中文。 */
  const regions = w.data.map(d => ({
    name: d.name,
    itemStyle: { areaColor: worldColor(worldT(d.value)) }
  }));

  // name → 中文 + 明细，给 tooltip 用
  const byName = {};
  w.data.forEach(d => { byName[d.name] = d; });

  draw('chartWorld', {
    animationDuration: 700,
    tooltip: {
      ...TIP,
      trigger: 'item',
      formatter: p => {
        const nm = (p.data && p.data.geoName) || p.name;
        const hit = byName[nm];
        if (!hit) return `<b>${nm}</b><br/><span style="color:${FX.mute}">未收录</span>`;
        const parts = (w.by_geo && w.by_geo[nm]) || null;
        const detail = parts && Object.keys(parts).length > 1
          ? '<br/><span style="color:' + FX.mute + ';font-size:11px">' +
            Object.keys(parts).map(k => k + ' ' + parts[k]).join(' / ') + '</span>'
          : '';
        return `<b>${hit.cn || nm}</b><br/>` +
               `<b style="color:${FX.accent}">${hit.value}</b> 部作品` + detail;
      }
    },
    // ① geo 组件：地图本体，按 regions 逐国上色
    geo: {
      map: 'world',
      roam: false,
      left: 'center', top: 'center', width: '100%', height: '100%',
      zoom: 1.12,
      label: { show: false },
      itemStyle: {
        // 没收录的国家
        areaColor: '#1b2129',
        borderColor: 'rgba(255,255,255,.14)',
        borderWidth: .6
      },
      // 有收录的国家：逐国覆盖颜色
      regions: regions,
      emphasis: {
        label: { show: true, color: FX.text, fontSize: 11.5, fontFamily: FONT },
        itemStyle: { areaColor: FX.accent, borderColor: '#fff' }
      },
      select: { disabled: true }
    },
    series: [{
      /* ② 一个「不可见」的散点系列：每个国家放一个极小的点，
         只为让 tooltip / 悬停能拿到数值和中文名。点本身不显示。 */
      type: 'scatter',
      coordinateSystem: 'geo',
      symbolSize: 1,
      itemStyle: { color: 'transparent' },
      silent: false,
      tooltip: { show: true },
      data: w.data.map(d => ({
        value: GEO_CENTER[d.name] || [],
        name: d.cn,
        geoName: d.name
      }))
    }]
  });
}

/* ======================= 02 类型 ======================= */
function buildGenre() {
  const rows = D.genreTop;
  draw('chartGenre', hBar(rows.map(r => r.name), rows.map(r => r.value), { unit: '部' }));
}

/* ======================= 03 年代（柱 + 线） ======================= */
function buildDecade() {
  const d = D.decade;
  draw('chartDecade', {
    animationDuration: 500,
    grid: { left: 4, right: 4, top: 26, bottom: 0, containLabel: true },
    legend: {
      top: 0, right: 0, itemWidth: 10, itemHeight: 6, itemGap: 12,
      textStyle: { color: FX.mute, fontSize: 11, fontFamily: FSANS }
    },
    tooltip: {
      ...TIP, trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,.04)' } },
      formatter: ps => {
        const i = ps[0].dataIndex;
        return `<b>${d.labels[i]}</b><br/>作品 ${d.counts[i]} 部` +
          `<br/><span style="color:${FX.mute}">其中有评分 ${d.rated[i]} 部</span>` +
          `<br/>平均分 <b style="color:${FX.accent}">${d.avg[i]}</b>`;
      }
    },
    xAxis: {
      type: 'category', data: d.labels,
      axisLine: { lineStyle: { color: FX.line } },
      axisTick: { show: false },
      axisLabel: { color: FX.dim, fontSize: 11, fontFamily: FSANS, interval: 0, rotate: 30 }
    },
    yAxis: [
      {
        type: 'value', name: '作品数',
        nameTextStyle: { color: FX.mute, fontSize: 11, fontFamily: FSANS },
        splitLine: { lineStyle: { color: FX.line } },
        axisLabel: { color: FX.mute, fontSize: 11, fontFamily: FSANS }
      },
      {
        // 平均分的分母是「有评分的作品数」，1990s / 2000s 只有 11 / 21 部有评分，
        // 所以这两点是虚线 + 小空心点，视觉上提示「样本少，别过度解读」
        type: 'value', name: '平均分',
        // 数据实际范围 8.54~9.38。下界压到 7.4、上界放到 9.5，把 8.54 的 2020s
        // 抬到图中部偏下，其余年代点落在上半区，折线就不会压到柱子上。
        min: 7.4, max: 9.5, splitNumber: 4,
        nameTextStyle: { color: FX.mute, fontSize: 11, fontFamily: FSANS },
        splitLine: { show: false },
        axisLabel: { color: FX.mute, fontSize: 11, fontFamily: FSANS }
      }
    ],
    series: [
      {
        name: '作品数', type: 'bar', data: d.counts, barWidth: '46%',
        itemStyle: { color: FX.bar, borderRadius: [1, 1, 0, 0] },
        emphasis: { itemStyle: { color: FX.accent } }
      },
      {
        /* 平均分折线画在右轴。★ 两个容易踩的点：
           1) 右轴 min/max 固定成 8.2~9.6，折线就会大幅上下摆、直接压在柱子上。
              改成「只把 7 个历史年代的 9.17~9.38 摊开」，折线走在上沿，
              和柱子不打架；2010s/2020s 的低点还可以借 labelPosition:'bottom' 落到柱子上方。
           2) 数字标签按值自动决定放在点的上方还是下方，避免把图例/标题顶出去。 */
        name: '平均分', type: 'line', yAxisIndex: 1, data: d.avg,
        symbol: 'circle', symbolSize: 6,
        lineStyle: { color: FX.accent, width: 1.8 },
        itemStyle: { color: FX.accent },
        label: {
          show: true, color: FX.dim,
          position: 'top', distance: 7,
          fontSize: 12, fontFamily: FSANS,
          formatter: p => p.value
        }
      }
    ]
  });
}

/* ======================= 04 评分 × 评价人数（散点） ======================= */
function buildScatter() {
  const pts = D.scatter;  // [[评分, 评价人数, 片名], ...]
  // 按 0.5 分一档分组上色：分数越高色越暖，一眼能看出「高分不一定高热度」
  const bins = {};
  pts.forEach(p => {
    const k = (Math.floor(p[0] / 0.5) * 0.5).toFixed(1);
    (bins[k] = bins[k] || []).push(p);
  });
  const keys = Object.keys(bins).sort();
  const tone = k => {
    const r = Math.min(1, (parseFloat(k) - 8.0) / 2.0);
    return `rgba(255,${Math.round(150 - 80 * r)},${Math.round(120 - 40 * r)},${0.28 + 0.5 * r})`;
  };
  draw('chartScatter', {
    animationDuration: 500,
    grid: { left: 4, right: 10, top: 10, bottom: 0, containLabel: true },
    tooltip: {
      ...TIP,
      formatter: p => `${p.data[2]}<br/>评分 <b style="color:${FX.accent}">${p.data[0]}</b>　` +
        `${(p.data[1] / 10000).toFixed(1)} 万人评价`
    },
    xAxis: {
      type: 'value', min: 7.8, max: 10,
      splitLine: { lineStyle: { color: FX.line } },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: FX.mute, fontSize: 11, fontFamily: FSANS }
    },
    yAxis: {
      type: 'log', min: 100,
      splitLine: { lineStyle: { color: FX.line } },
      axisLabel: {
        color: FX.mute, fontSize: 11, fontFamily: FSANS,
        formatter: v => (v >= 10000 ? (v / 10000) + '万' : v)
      }
    },
    series: keys.map(k => ({
      name: k + ' 分',
      type: 'scatter',
      data: bins[k],
      symbolSize: 4,
      itemStyle: { color: tone(k) },
      emphasis: { itemStyle: { color: FX.accent }, scale: 1.9 }
    }))
  });
}

/* ======================= 05 年份趋势 ======================= */
function buildYear() {
  const y = D.yearTrend;
  draw('chartYear', {
    animationDuration: 500,
    grid: { left: 4, right: 10, top: 10, bottom: 0, containLabel: true },
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: FX.mute } } },
    xAxis: {
      type: 'category', data: y.labels, boundaryGap: false,
      axisLine: { lineStyle: { color: FX.line } }, axisTick: { show: false },
      axisLabel: { color: FX.mute, fontSize: 11, fontFamily: FSANS, interval: 1 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: FX.line } },
      axisLabel: { color: FX.mute, fontSize: 11, fontFamily: FSANS }
    },
    series: [{
      type: 'line', data: y.values, smooth: true, symbol: 'none',
      lineStyle: { color: FX.accent, width: 1.6 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(255,107,74,.34)' },
          { offset: 1, color: 'rgba(255,107,74,0)' }
        ])
      }
    }]
  });
}

/* ======================= 06 国家 TOP15 ======================= */
function buildCountry() {
  const rows = D.world.top.slice(0, 15);
  /* 15 行铺满一张 1080 高的大卡片，行距撑开会比挤在顶部好看得多，
     所以 spread:true（hBar 里把 grid 上下各留 18px 呼吸位）。 */
  draw('chartCountry', hBar(rows.map(r => r.name), rows.map(r => r.value),
    { unit: '部', labelSize: 14, spread: true }));
}

/* ======================= 07 词云 ======================= */
function buildWord() {
  const words = D.wordCloud;
  const el = document.getElementById('chartWord');
  // 容器宽高：优先用 clientWidth/Height；万一还没量出尺寸（0），
  // 用父卡片的尺寸兜底，绝不能拿 0 去算排版。
  const W = el.clientWidth || el.parentElement.clientWidth || 740;
  const H = el.clientHeight || el.parentElement.clientHeight || 850;
  // 按词频分三档，只有最高一档用强调色（不随机取色，否则每次刷新都变）
  const maxV = words[0] ? words[0].value : 1;
  const colorOf = v => (v >= maxV * 0.55 ? FX.accent : (v >= maxV * 0.3 ? FX.dim : FX.mute));

  /* ★ 为什么这里不用 ECharts 的 wordCloud 而自己用 canvas 画：
       echarts-wordcloud 必须先量出「每个词在目标字号下的宽高」才能排版，
       它依赖容器尺寸与 canvas 测量 API 的时序；在本项目「多屏切换 + 离线
       file:// 打开」的场景里这一步经常算出 0 尺寸，结果是 100 个词全部挤在
       (0,0) —— 屏幕上看就是一整片空白，而且不报错、很难查。
       自己画只有几十行，且结果稳定：按词频定字号，从中心螺旋向外找空位，
       放不下就跳过。想换配色只改 colorOf()。 */
  const dpr = window.devicePixelRatio || 1;

  // 复用一张 canvas：第一次进来新建，之后每次重画只清空
  let cv = el.querySelector('canvas.wc');
  if (!cv) {
    el.innerHTML = '';
    cv = document.createElement('canvas');
    cv.className = 'wc';
    cv.style.cssText = 'display:block;width:100%;height:100%';
    el.appendChild(cv);
  }
  cv.width = Math.round(W * dpr);
  cv.height = Math.round(H * dpr);
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  // 字号：最高的词占容器高度的 9%，逐级递减，最小 15px
  // （2026-10-20 由 13px 提到 15px：15px 以下的中文在近黑底上基本认不出笔画）
  const fsMax = Math.max(26, Math.min(76, Math.round(H * 0.095)));
  const fsMin = 15;
  const n = words.length;
  const size = i => Math.round(fsMax - (fsMax - fsMin) * (i / Math.max(1, n - 1)) * 0.85);

  /* 逐个词找位置：从画布中心出发，沿阿基米德螺旋向外试探，
     用「已占位矩形」做碰撞检测，找到不重叠的位置就画上去。 */
  const placed = [];
  const hit = (x, y, w, h) => placed.some(r =>
    x < r.x + r.w && x + w > r.x && y < r.y + r.h && y + h > r.y);

  words.forEach((w, i) => {
    const fsz = size(i);
    ctx.font = `${fsz}px ${FONT}`;
    const tw = ctx.measureText(w.name).width + 6;   // 留 3px 边
    const th = fsz * 1.22;

    // 螺旋：半径每圈增加 3px，角度每步 0.35 弧度
    for (let r = 0, a = 0; r < Math.max(W, H); r += 3, a += 0.35) {
      const x = W / 2 + Math.cos(a) * r - tw / 2;
      const y = H / 2 + Math.sin(a) * r - th / 2;
      if (x < 4 || y < 4 || x + tw > W - 4 || y + th > H - 4) continue;
      if (hit(x, y, tw, th)) continue;
      placed.push({ x, y, w: tw, h: th });
      ctx.fillStyle = colorOf(w.value);
      ctx.textBaseline = 'top';
      ctx.fillText(w.name, x + 3, y + fsz * 0.1);
      break;
    }
  });
}

/* ======================= 08 双分母星级堆叠条 ======================= */
/* 两条几乎重合的横条：
   上 = 942 部作品的「五星~一星占比」
   下 = 4695 条短评的「五星~一星占比」
   都用 100% 归一化，用来对比「作品评分」与「用户打分」是否一致。 */
function buildStarDual() {
  const s = D.starDual;
  // 从五星到一星用同一色阶（强调色 → 中性灰），保证两条视觉一致
  const palette = ['#ff6b4a', '#c2503a', '#6c3b30', '#3a3f46', '#262b31'];
  draw('chartStarDual', {
    animationDuration: 600,
    grid: { left: 4, right: 8, top: 26, bottom: 0, containLabel: true },
    tooltip: {
      ...TIP, trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,.04)' } },
      formatter: ps => {
        const head = ps[0].axisValue === '作品级' ? `作品级（${s.works_n} 部）` : `短评级（${s.cmts_n} 条）`;
        return head + '<br/>' + ps.slice().reverse()
          .map(p => `${p.marker}${p.seriesName}　<b>${p.value}%</b>`).join('<br/>');
      }
    },
    xAxis: {
      type: 'value', max: 100, position: 'top',
      axisLabel: { formatter: '{value}%', color: FX.mute, fontSize: 11, fontFamily: FSANS },
      splitLine: { lineStyle: { color: FX.line } }
    },
    yAxis: {
      type: 'category', data: ['作品级', '短评级'],
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: FX.dim, fontSize: 13, fontFamily: FONT }
    },
    series: s.labels.map((lab, i) => ({
      name: lab, type: 'bar', stack: 'a', barWidth: 22,
      itemStyle: { color: palette[i] },
      label: {
        show: true,
        formatter: p => (p.value >= 5 ? p.value.toFixed(0) + '%' : ''),  // 太窄的不显示
        color: i < 2 ? '#12100f' : FX.dim,
        fontSize: 11.5, fontFamily: FSANS
      },
      data: [s.works[i], s.cmts[i]]   // 顺序与 y 轴类目 ['作品级','短评级'] 一一对应
    }))
  });
}

/* ======================= 09 建模对比条 ======================= */
/* 四个数字同框：瞎猜 / 只猜多数类 / 同片多数票 / 文本模型 */
function buildModelBar() {
  const m = D.model;
  const rows = [
    ['瞎猜（50%）', m.random],
    ['只猜多数类', m.baseline],
    ['同片其他短评多数票', m.same_movie],
    ['文本模型（本项目）', m.auc]
  ];
  draw('chartModelBar', {
    animationDuration: 600,
    /* ★ 原来是 min 0.45 / max 0.70：四条柱子都挤在右半边一小段里，
       左边一半全空，看着像图没画完。现在按「0.5 = 瞎猜」画基线，
       横轴直接取 0.5~0.66，四根的差异才看得出来。 */
    grid: { left: 0, right: 64, top: 4, bottom: 0, containLabel: true },
    xAxis: { type: 'value', min: 0, max: 0.70, show: false },
    yAxis: {
      type: 'category', data: rows.map(r => r[0]).reverse(),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: FX.dim, fontSize: 12.5, fontFamily: FONT, margin: 10 }
    },
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'none' },
      formatter: p => `${p[0].name}<br/>AUC <b style="color:${FX.accent}">${p[0].value}</b>` },
    series: [{
      // ★ 柱宽别再写死 11px：卡片高度会随窗口变，写死的话窗口一放大，
      // 四根柱子之间就裂出大片空白。maxWidth 让柱子最多 26px，其余按比例分。
      type: 'bar', barWidth: '32%', barMaxWidth: 26,
      data: rows.map(r => r[1]).reverse(),
      itemStyle: {
        // 倒序后 dataIndex 0 = 最后一行 = 文本模型
        color: p => (p.dataIndex === 0 ? FX.accent : FX.bar),
        borderRadius: [0, 1, 1, 0]
      },
      label: {
        show: true, position: 'right', color: FX.dim,
        fontSize: 12.5, fontFamily: FSANS, formatter: p => p.value.toFixed(3)
      },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: FX.mute, type: 'dashed', width: 1 },
        label: { show: false },
        data: [{ xAxis: 0.5 }]   // 0.5 = 完全随机
      }
    }]
  });
}

/* ======================= 10 混淆矩阵 ======================= */
function buildConfusion() {
  const m = D.model;
  const labs = m.confusion_labels;           // ['中评','好评','差评']
  const cells = [];
  m.confusion.forEach((row, i) => row.forEach((v, j) => cells.push([j, i, v])));
  const maxV = Math.max(...m.confusion.flat());
  draw('chartConfusion', {
    animationDuration: 500,
    grid: { left: 6, right: 6, top: 26, bottom: 6, containLabel: true },
    tooltip: {
      ...TIP,
      formatter: p => `真实「${labs[p.data[1]]}」<br/>被预测为「${labs[p.data[0]]}」<br/>` +
        `<b style="color:${FX.accent}">${p.data[2]}</b> 条`
    },
    xAxis: {
      type: 'category', data: labs, position: 'top',
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: FX.dim, fontSize: 11.5, fontFamily: FONT }
    },
    yAxis: {
      type: 'category', data: labs, inverse: true,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: FX.dim, fontSize: 11.5, fontFamily: FONT }
    },
    visualMap: {
      show: false, min: 0, max: maxV,
      inRange: { color: ['#14181d', '#3a2420', '#8c3a2b', FX.accent] }
    },
    series: [{
      type: 'heatmap',
      data: cells,
      label: {
        show: true, fontSize: 12.5, fontFamily: FSANS,
        formatter: p => p.data[2],
        color: p => (p.data[2] > maxV * 0.25 ? '#12100f' : FX.dim)
      },
      itemStyle: { borderColor: '#0a0b0d', borderWidth: 2 }
    }]
  });
}

/* ======================= 尺寸自适应 ======================= */
/* 舞台是等比缩放的（见 main.js 的 fitStage），窗口变化时图也要重算尺寸 */
window.addEventListener('resize', () => Object.values(CHARTS).forEach(c => c.resize()));
