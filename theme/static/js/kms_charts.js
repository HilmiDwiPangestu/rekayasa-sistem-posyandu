(function (global) {
  'use strict';

  const CURVES = [
    ['sd3neg', '-3 SD', '#b91c1c'],
    ['sd2neg', '-2 SD', '#d97706'],
    ['sd1neg', '-1 SD', '#64748b'],
    ['median', 'Median', '#15803d'],
    ['sd1', '+1 SD', '#64748b'],
    ['sd2', '+2 SD', '#d97706'],
    ['sd3', '+3 SD', '#b91c1c']
  ];
  const CHILD = '#2563eb';

  function num(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function childSeries(points, key) {
    return (Array.isArray(points) ? points : [])
      .map((p) => ({ x: num(p.bulan), y: num(p[key]), tanggal: p.tanggal || '-' }))
      .filter((p) => p.x !== null && p.y !== null && p.x >= 0 && p.x <= 60)
      .sort((a, b) => a.x - b.x);
  }

  function standardSeries(std, key) {
    if (!std || !Array.isArray(std.month) || !Array.isArray(std[key])) return [];
    return std.month
      .map((m, i) => ({ x: num(m), y: num(std[key][i]) }))
      .filter((p) => p.x !== null && p.y !== null);
  }

  function themeColors() {
    const dark = document.documentElement.classList.contains('dark');
    return dark
      ? { grid: 'rgba(148,163,184,.18)', axis: '#94a3b8', text: '#cbd5e1' }
      : { grid: 'rgba(100,116,139,.16)', axis: '#64748b', text: '#475569' };
  }

  function niceStep(range, targetTicks) {
    if (!Number.isFinite(range) || range <= 0) return 1;
    const rough = range / Math.max(targetTicks, 2);
    const power = Math.pow(10, Math.floor(Math.log10(rough)));
    const fraction = rough / power;
    let nice = 10;
    if (fraction <= 1) nice = 1;
    else if (fraction <= 2) nice = 2;
    else if (fraction <= 5) nice = 5;
    return nice * power;
  }

  function draw(canvasId, standard, child, yTitle, childLabel, decimals) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const parent = canvas.parentElement;
    if (!parent) return;

    // UI_MOBILE_V5: use the actual chart stage, never force a 320px canvas
    // inside a narrower mobile card and never include parent padding in the
    // canvas dimensions. This prevents the canvas from spilling into the next title.
    const rect = parent.getBoundingClientRect();
    const style = global.getComputedStyle ? global.getComputedStyle(parent) : null;
    const padX = style ? (parseFloat(style.paddingLeft || '0') + parseFloat(style.paddingRight || '0')) : 0;
    const padY = style ? (parseFloat(style.paddingTop || '0') + parseFloat(style.paddingBottom || '0')) : 0;
    const cssWidth = Math.max(180, Math.floor((parent.clientWidth || rect.width || 0) - padX));
    const cssHeight = Math.max(220, Math.floor((parent.clientHeight || rect.height || 0) - padY));
    const dpr = Math.max(1, global.devicePixelRatio || 1);

    canvas.width = Math.round(cssWidth * dpr);
    canvas.height = Math.round(cssHeight * dpr);
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.display = 'block';

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    const theme = themeColors();
    const isMobile = cssWidth < 520;
    const margin = isMobile
      ? { left: 42, right: 8, top: 10, bottom: 46 }
      : { left: 58, right: 16, top: 14, bottom: 52 };
    const plotW = Math.max(80, cssWidth - margin.left - margin.right);
    const plotH = Math.max(90, cssHeight - margin.top - margin.bottom);

    const allY = [];
    CURVES.forEach(([key]) => standardSeries(standard, key).forEach((p) => allY.push(p.y)));
    child.forEach((p) => allY.push(p.y));

    if (!allY.length) {
      ctx.fillStyle = theme.text;
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Data standar tidak tersedia.', cssWidth / 2, cssHeight / 2);
      return;
    }

    let yMin = Math.min.apply(null, allY);
    let yMax = Math.max.apply(null, allY);
    const pad = Math.max((yMax - yMin) * 0.08, 0.5);
    yMin -= pad;
    yMax += pad;

    const step = niceStep(yMax - yMin, 6);
    yMin = Math.floor(yMin / step) * step;
    yMax = Math.ceil(yMax / step) * step;

    const xPx = (x) => margin.left + (x / 60) * plotW;
    const yPx = (y) => margin.top + ((yMax - y) / (yMax - yMin)) * plotH;

    ctx.lineWidth = 1;
    ctx.font = isMobile ? '9px sans-serif' : '10px sans-serif';
    ctx.fillStyle = theme.text;
    ctx.strokeStyle = theme.grid;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    for (let m = 0; m <= 60; m += (isMobile ? 12 : 6)) {
      const x = xPx(m);
      ctx.beginPath();
      ctx.moveTo(x, margin.top);
      ctx.lineTo(x, margin.top + plotH);
      ctx.stroke();
      ctx.fillText(String(m), x, margin.top + plotH + 8);
    }

    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    const tickCount = Math.round((yMax - yMin) / step);
    for (let i = 0; i <= tickCount; i += 1) {
      const value = yMin + i * step;
      const y = yPx(value);
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + plotW, y);
      ctx.stroke();
      ctx.fillText(value.toFixed(decimals), margin.left - 8, y);
    }

    ctx.strokeStyle = theme.axis;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(margin.left, margin.top);
    ctx.lineTo(margin.left, margin.top + plotH);
    ctx.lineTo(margin.left + plotW, margin.top + plotH);
    ctx.stroke();

    ctx.fillStyle = theme.text;
    ctx.font = isMobile ? '10px sans-serif' : '11px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillText('Umur (bulan penuh)', margin.left + plotW / 2, margin.top + plotH + 30);

    ctx.save();
    ctx.translate(isMobile ? 13 : 16, margin.top + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(yTitle, 0, 0);
    ctx.restore();

    CURVES.forEach(([key, label, color]) => {
      const series = standardSeries(standard, key);
      if (!series.length) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = key === 'median' ? 2.2 : 1.25;
      ctx.setLineDash(key === 'median' ? [] : [5, 4]);
      ctx.beginPath();
      series.forEach((p, index) => {
        const x = xPx(p.x);
        const y = yPx(p.y);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });

    if (child.length) {
      ctx.strokeStyle = CHILD;
      ctx.fillStyle = CHILD;
      ctx.lineWidth = 3;
      ctx.setLineDash([]);
      ctx.beginPath();
      child.forEach((p, index) => {
        const x = xPx(p.x);
        const y = yPx(p.y);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      if (child.length > 1) ctx.stroke();
      child.forEach((p) => {
        const x = xPx(p.x);
        const y = yPx(p.y);
        ctx.beginPath();
        ctx.arc(x, y, 4.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.4;
        ctx.stroke();
      });
    }

    // UI_MOBILE_V5: legend is rendered in HTML where needed.
    ctx.setLineDash([]);
  }

  function renderTriple(payload, ids) {
    payload = payload || {};
    ids = ids || {};
    const points = Array.isArray(payload.points) ? payload.points : [];
    draw(ids.bbu, payload.bbu, childSeries(points, 'berat'), 'Berat badan (kg)', 'BB anak', 1);
    draw(ids.tbu, payload.pbu_tbu, childSeries(points, 'tinggi'), 'Panjang/Tinggi (cm)', 'PB/TB anak', 1);
    draw(ids.imtu, payload.imtu, childSeries(points, 'imt'), 'IMT (kg/m²)', 'IMT anak', 1);
  }

  global.KMSCharts = { renderTriple: renderTriple };
})(window);
