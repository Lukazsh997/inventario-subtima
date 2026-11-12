// Gráficos do dashboard (Chart.js local). Cada <canvas data-chart="tipo" data-source="id-do-json">.
// Paleta categórica fixa (validada para daltonismo): série 1 azul, série 2 laranja; nunca reciclada.
(function () {
  "use strict";
  var SERIES = ["#2a78d6", "#eb6834"];
  var INK = "#52514e";
  var GRID = "rgba(11, 11, 11, 0.08)";

  function read(id) { return JSON.parse(document.getElementById(id).textContent); }

  function baseOptions(horizontal) {
    var valueAxis = { beginAtZero: true, ticks: { color: INK, precision: 0 }, grid: { color: GRID }, border: { display: false } };
    var categoryAxis = { ticks: { color: INK, autoSkip: true, maxRotation: 0 }, grid: { display: false }, border: { color: GRID } };
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#0b0b0b", padding: 10, cornerRadius: 6, displayColors: true }
      },
      scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis }
    };
  }

  function bar(color, label, values) {
    return {
      label: label, data: values, backgroundColor: color, borderRadius: 4, borderSkipped: "start",
      maxBarThickness: 28, categoryPercentage: 0.7, barPercentage: 0.9
    };
  }

  var builders = {
    // Entradas x saídas: duas séries lado a lado, com legenda.
    pair: function (data) {
      var options = baseOptions(false);
      options.plugins.legend = { display: true, position: "top", align: "start",
        labels: { color: INK, boxWidth: 12, boxHeight: 12, useBorderRadius: true, borderRadius: 3 } };
      return { type: "bar", data: { labels: data.labels, datasets: [
        bar(SERIES[0], "Entradas", data.entries), bar(SERIES[1], "Saídas", data.exits)] }, options: options };
    },
    columns: function (data, label) {
      return { type: "bar", data: { labels: data.labels, datasets: [bar(SERIES[0], label, data.values)] },
        options: baseOptions(false) };
    },
    rows: function (data, label) {
      return { type: "bar", data: { labels: data.labels, datasets: [bar(SERIES[0], label, data.values)] },
        options: baseOptions(true) };
    },
    line: function (data, label) {
      var options = baseOptions(false);
      return { type: "line", data: { labels: data.labels, datasets: [{
        label: label, data: data.values, borderColor: SERIES[0], backgroundColor: SERIES[0], borderWidth: 2,
        pointRadius: 3, pointHoverRadius: 5, tension: 0.25, fill: false }] }, options: options };
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    if (!window.Chart) { return; }
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var data = read(canvas.dataset.source);
      if (!data.labels.length) { return; }
      new Chart(canvas, builders[canvas.dataset.chart](data, canvas.dataset.label || ""));
    });
  });
})();
