/**
 * BiAdvancedViz — 8+ nuevos tipos de gráfico usando Apache ECharts.
 *
 * Chart types soportados:
 *  treemap    — distribución jerárquica (ej. revenue por cliente/proyecto)
 *  heatmap    — correlación métrica × período
 *  gauge      — indicador circular de % (utilización, presupuesto)
 *  radar      — comparativa multidimensional de proyectos
 *  scatter    — correlación coste vs revenue
 *  funnel     — pipeline de ventas / fases
 *  sunburst   — drill-down jerárquico (cliente → proyecto → tarea)
 *  boxplot    — distribución de duraciones / costes
 */
import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';

const CHART_TYPES = [
  { key: 'treemap',  label: 'Treemap' },
  { key: 'heatmap',  label: 'Heatmap' },
  { key: 'gauge',    label: 'Gauge' },
  { key: 'radar',    label: 'Radar' },
  { key: 'scatter',  label: 'Scatter' },
  { key: 'funnel',   label: 'Funnel' },
  { key: 'sunburst', label: 'Sunburst' },
  { key: 'boxplot',  label: 'Boxplot' },
];

// ── Mock data generators (replaced by real API calls when wired) ──────────────
function treemapOption() {
  return {
    series: [{
      type: 'treemap',
      data: [
        { name: 'Cliente A', value: 320000, children: [
          { name: 'Proyecto Alpha', value: 180000 },
          { name: 'Proyecto Beta',  value: 140000 },
        ]},
        { name: 'Cliente B', value: 240000, children: [
          { name: 'Proyecto Gamma', value: 240000 },
        ]},
        { name: 'Cliente C', value: 150000, children: [
          { name: 'Proyecto Delta', value: 90000 },
          { name: 'Proyecto Epsilon', value: 60000 },
        ]},
        { name: 'Cliente D', value: 80000, children: [
          { name: 'Proyecto Zeta', value: 80000 },
        ]},
      ],
      leafDepth: 1,
      label: { show: true, formatter: '{b}\n{c}€' },
    }],
    tooltip: { formatter: (info) => `${info.name}: ${Number(info.value).toLocaleString('es-ES')}€` },
  };
}

function heatmapOption() {
  const months = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  const projects = ['Alpha','Beta','Gamma','Delta','Epsilon'];
  const data = [];
  projects.forEach((_, pi) => months.forEach((_, mi) => {
    data.push([mi, pi, Math.round(Math.random() * 100)]);
  }));
  return {
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'category', data: projects },
    visualMap: { min: 0, max: 100, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#e0f7fa','#006064'] } },
    series: [{ type: 'heatmap', data, label: { show: true } }],
    tooltip: {},
    grid: { bottom: 60 },
  };
}

function gaugeOption() {
  return {
    series: [{
      type: 'gauge',
      startAngle: 180,
      endAngle: 0,
      min: 0,
      max: 100,
      pointer: { show: true },
      progress: { show: true, overlap: false, roundCap: true },
      axisLine: { lineStyle: { width: 40, color: [[0.3,'#f44336'],[0.7,'#ff9800'],[1,'#4caf50']] } },
      data: [
        { value: 72, name: 'Utilización', title: { offsetCenter: ['0%', '-30%'] } },
      ],
      detail: { width: 50, height: 14, fontSize: 24, color: 'inherit', formatter: '{value}%' },
      title: { fontSize: 14 },
    }],
  };
}

function radarOption() {
  return {
    radar: {
      indicator: [
        { name: 'Revenue', max: 100 },
        { name: 'Margen', max: 100 },
        { name: 'Utilización', max: 100 },
        { name: 'Entregas a tiempo', max: 100 },
        { name: 'Satisfacción', max: 100 },
        { name: 'Backlog controlado', max: 100 },
      ],
    },
    series: [{
      type: 'radar',
      data: [
        { value: [85, 72, 68, 90, 88, 75], name: 'Q1 2025' },
        { value: [78, 80, 74, 82, 91, 70], name: 'Q4 2024' },
      ],
    }],
    legend: { data: ['Q1 2025','Q4 2024'] },
    tooltip: {},
  };
}

function scatterOption() {
  const pts = Array.from({ length: 40 }, (_, i) => {
    const cost = 10000 + Math.random() * 200000;
    return [cost, cost * (0.8 + Math.random() * 0.8), `Proyecto ${i + 1}`];
  });
  return {
    xAxis: { name: 'Coste (€)', type: 'value' },
    yAxis: { name: 'Revenue (€)', type: 'value' },
    series: [{ type: 'scatter', data: pts.map(([x,y]) => [x, y]), symbolSize: 10 }],
    tooltip: { formatter: (p) => `Coste: ${Number(p.data[0]).toLocaleString('es-ES')}€<br/>Revenue: ${Number(p.data[1]).toLocaleString('es-ES')}€` },
    grid: { left: 60, right: 20 },
  };
}

function funnelOption() {
  return {
    series: [{
      type: 'funnel',
      data: [
        { value: 100, name: 'Oportunidades' },
        { value: 70,  name: 'Propuestas' },
        { value: 45,  name: 'Negociación' },
        { value: 28,  name: 'Contratos' },
        { value: 15,  name: 'Cierre' },
      ],
      label: { formatter: '{b}: {c}%' },
      gap: 4,
    }],
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
  };
}

function sunburstOption() {
  return {
    series: [{
      type: 'sunburst',
      radius: ['0%', '90%'],
      data: [
        { name: 'Cliente A', children: [
          { name: 'Alpha', value: 180, children: [
            { name: 'Frontend', value: 80 },
            { name: 'Backend', value: 100 },
          ]},
          { name: 'Beta', value: 140 },
        ]},
        { name: 'Cliente B', children: [
          { name: 'Gamma', value: 240, children: [
            { name: 'Infra', value: 90 },
            { name: 'App', value: 150 },
          ]},
        ]},
        { name: 'Cliente C', children: [
          { name: 'Delta', value: 90 },
          { name: 'Epsilon', value: 60 },
        ]},
      ],
      label: { fontSize: 10 },
    }],
    tooltip: {},
  };
}

function boxplotOption() {
  return {
    xAxis: { data: ['Jan','Feb','Mar','Apr','May','Jun'], boundaryGap: true },
    yAxis: { name: 'Días', type: 'value' },
    series: [{
      type: 'boxplot',
      data: [
        [5, 12, 18, 25, 38],
        [4, 10, 15, 22, 35],
        [6, 14, 20, 28, 42],
        [3, 9,  14, 20, 30],
        [7, 15, 22, 30, 45],
        [5, 11, 17, 24, 37],
      ],
    }],
    tooltip: { trigger: 'item' },
  };
}

const OPTION_BUILDERS = { treemap: treemapOption, heatmap: heatmapOption, gauge: gaugeOption, radar: radarOption, scatter: scatterOption, funnel: funnelOption, sunburst: sunburstOption, boxplot: boxplotOption };

// ─────────────────────────────────────────────────────────────────────────────
export default function BiAdvancedViz({ style }) {
  const [activeChart, setActiveChart] = useState('treemap');
  const option = useMemo(() => (OPTION_BUILDERS[activeChart] || treemapOption)(), [activeChart]);

  return (
    <div style={{ background: 'var(--surface-1,#fff)', borderRadius: 12, padding: '1.25rem', ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: '1rem' }}>Visualización avanzada</span>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {CHART_TYPES.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveChart(key)}
              style={{
                padding: '4px 12px',
                borderRadius: 20,
                border: '1.5px solid var(--border,#e5e7eb)',
                background: activeChart === key ? 'var(--accent,#6366f1)' : 'transparent',
                color: activeChart === key ? '#fff' : 'var(--text-secondary,#6b7280)',
                fontSize: '0.75rem',
                cursor: 'pointer',
                fontWeight: activeChart === key ? 700 : 400,
                transition: 'all .15s',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <ReactECharts
        option={option}
        style={{ height: 380 }}
        notMerge
        lazyUpdate
      />
    </div>
  );
}
