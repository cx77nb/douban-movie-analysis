/* ==========================================================================
   main.js —— 「启动 + 自适应」脚本（图表本身在 js/charts.js）
   --------------------------------------------------------------------------
   它干四件事：
     1. fitStage()  把 1920×1080 的舞台等比缩放到当前窗口（大屏不变形）
     2. fillKpi()   把 KPI 卡片的数字填进 index.html 的 #kpiRow
     3. tick()      顶栏时钟
     4. 窗口大小变化时重新缩放 + 让所有图表跟着 resize
   ========================================================================== */

const STAGE_W = 1920;         // 舞台设计宽度（和 css/style.css 里 #stage 一致）
const STAGE_H = 1080;         // 舞台设计高度

/* 1. 等比缩放：让整块大屏始终完整显示在窗口里 */
function fitStage() {
  const scale = Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H);
  const stage = document.getElementById('stage');
  stage.style.transform = 'scale(' + scale + ')';
  // 左右居中（缩放后剩余的空间平均分给两边）
  stage.style.left = (window.innerWidth - STAGE_W * scale) / 2 + 'px';
}

/* 2. 填 KPI 卡片：想加一张卡，就在这里多加一行 */
const KPI_LIST = [
  { key: 'works',          lab: '作品总数' },
  { key: 'movies',         lab: '电影' },
  { key: 'tvs',            lab: '剧集' },
  { key: 'comments',       lab: '短评条数' },
  { key: 'top250',         lab: '豆瓣 Top250' },
  { key: 'avg_rating',     lab: '平均评分' }
];

function fillKpi() {
  const box = document.getElementById('kpiRow');
  box.innerHTML = KPI_LIST.map(item =>
    '<div class="kpi"><div class="val">' + D.kpi[item.key] + '</div>' +
    '<div class="lab">' + item.lab + '</div></div>'
  ).join('');
}

/* 3. 时钟 + 数据更新时间 */
function tick() {
  const now = new Date();
  const p = n => (n < 10 ? '0' + n : '' + n);
  document.getElementById('clock').textContent =
    p(now.getHours()) + ':' + p(now.getMinutes()) + ':' + p(now.getSeconds());
  document.getElementById('dataTime').textContent = '数据更新：' + D.updated;
}

/* 3.5 地图标题上补一句：海外用户不在中国地图里 */
function noteMapTitle() {
  const h3 = document.querySelector('#chartMap').parentNode.querySelector('h3');
  if (h3) h3.textContent += '（另有海外 ' + D.overseas + ' 条未入图）';
}

/* 4. 窗口尺寸变化：重新缩放 + 重画（ECharts 必须手动 resize） */
window.addEventListener('resize', function () {
  fitStage();
  CHARTS.forEach(function (c) { c.resize(); });
});

/* 页面加载完成后再画图，保证容器高度已经算好 */
window.addEventListener('load', function () {
  fitStage();
  fillKpi();
  noteMapTitle();
  tick();
  setInterval(tick, 1000);
  initAllCharts();          // 来自 charts.js：一次画出所有图
});
