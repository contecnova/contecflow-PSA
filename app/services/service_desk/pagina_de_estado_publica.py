"""Página de estado pública y su widget para webs de clientes (revisión 2026-11).

Medido antes:
- `/status` llevaba su JavaScript en línea y la propia API lo prohíbe
  (`script-src 'self'`): la página no pintaba nada.
- Leía `data.overall_status` y la API lo devuelve dentro de `data`: aunque se
  ejecutara, siempre decía «no hay componentes».
- El widget (`/status/embed.js`) salía con `Cross-Origin-Resource-Policy:
  same-origin`, así que la web de un cliente no podía cargarlo; tomaba la API
  de `window.location.origin`, que en esa web es la del cliente; y metía los
  nombres de los componentes en su página sin escapar.
- Había un segundo widget (`/api/v1/sd/status-page/embed.js`) que nadie
  repartía.

Ahora: la página no lleva código en línea (`/status/page.js`), los textos van
en el idioma de la empresa (`DEFAULT_LANGUAGE`), el widget sabe de dónde viene
por su propio `src` y escapa lo que pinta, y `GET /api/v1/sd/status-page` deja
leer a cualquier origen (es pública y no lleva credenciales).
"""
from __future__ import annotations

import html
import json

from app.services.formato_regional import IDIOMA_DE_RESPALDO

TEXTOS = {
    "es": {"titulo": "Estado del servicio", "cargando": "Cargando…", "general": "Estado general",
           "sin_componentes": "No hay componentes públicos.", "no_disponible": "No disponible",
           "error": "No se pudo cargar el estado", "actualizado": "Actualizado",
           "operational": "operativo", "degraded_performance": "rendimiento degradado",
           "partial_outage": "caída parcial", "major_outage": "caída grave", "maintenance": "mantenimiento"},
    "en": {"titulo": "Service status", "cargando": "Loading…", "general": "Overall",
           "sin_componentes": "No public components.", "no_disponible": "Unavailable",
           "error": "Could not load the status", "actualizado": "Updated",
           "operational": "operational", "degraded_performance": "degraded performance",
           "partial_outage": "partial outage", "major_outage": "major outage", "maintenance": "maintenance"},
    "zh": {"titulo": "服务状态", "cargando": "加载中…", "general": "总体状态",
           "sin_componentes": "暂无公开组件。", "no_disponible": "不可用",
           "error": "无法加载状态", "actualizado": "更新时间",
           "operational": "正常", "degraded_performance": "性能下降",
           "partial_outage": "部分中断", "major_outage": "严重中断", "maintenance": "维护中"},
}


def idioma_de(db, org_id) -> str:
    from app.services.settings_service import get_runtime_str
    idioma = (get_runtime_str(db, "DEFAULT_LANGUAGE", org_id) or IDIOMA_DE_RESPALDO)[:2]
    return idioma if idioma in TEXTOS else IDIOMA_DE_RESPALDO


def pagina(idioma: str) -> str:
    """La página: sin código en línea; los textos van en `data-textos`."""
    tx = TEXTOS.get(idioma, TEXTOS[IDIOMA_DE_RESPALDO])
    e = html.escape
    return f"""<!doctype html>
<html lang="{e(idioma)}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(tx['titulo'])}</title>
<style>
:root {{ --line:#24324a; --txt:#e5e7eb; --muted:#93a3b8; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --maint:#6366f1; }}
body {{ margin:0; background:#0b1220; color:var(--txt); font:14px/1.5 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu; }}
.wrap {{ max-width:980px; margin:0 auto; padding:32px 16px 40px; }}
.head {{ display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:20px; }}
.title {{ font-size:28px; font-weight:800; }}
.badge {{ padding:6px 12px; border-radius:999px; border:1px solid var(--line); font-size:12px; }}
.group {{ margin-top:20px; border:1px solid var(--line); border-radius:14px; overflow:hidden; }}
.group h2 {{ margin:0; padding:12px 16px; font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); border-bottom:1px solid var(--line); }}
.row {{ display:flex; justify-content:space-between; gap:10px; padding:12px 16px; border-bottom:1px solid #1b2940; }}
.row:last-child {{ border-bottom:0; }}
.name {{ font-weight:700; }} .desc {{ color:var(--muted); font-size:12px; margin-top:2px; }}
.status {{ font-weight:700; font-size:12px; text-transform:uppercase; }}
.operational {{ color:var(--ok); }} .degraded_performance {{ color:var(--warn); }} .partial_outage,.major_outage {{ color:var(--bad); }} .maintenance {{ color:var(--maint); }}
.foot {{ margin-top:14px; color:var(--muted); font-size:12px; }}
.err {{ border:1px solid #7f1d1d; color:#fecaca; border-radius:10px; padding:10px 12px; }}
</style>
</head>
<body data-textos="{e(json.dumps(tx, ensure_ascii=False))}">
<div class="wrap">
  <div class="head"><div class="title">{e(tx['titulo'])}</div><div id="overall" class="badge">{e(tx['cargando'])}</div></div>
  <div id="content"></div>
  <div id="foot" class="foot"></div>
</div>
<script src="/status/page.js"></script>
</body>
</html>"""


def guion_de_pagina(api_v1: str) -> str:
    return """(function () {
  var tx = JSON.parse(document.body.getAttribute('data-textos') || '{}');
  var org = new URLSearchParams(window.location.search).get('org');
  var api = %s + '/sd/status-page' + (org ? '?org=' + encodeURIComponent(org) : '');
  var $content = document.getElementById('content'), $overall = document.getElementById('overall'), $foot = document.getElementById('foot');
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (m) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]; }); }
  function estado(s) { return tx[s] || String(s || '').replace(/_/g, ' '); }
  fetch(api)
    .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
    .then(function (cuerpo) {
      var data = cuerpo.data || cuerpo;
      $overall.className = 'badge ' + esc(data.overall_status);
      $overall.textContent = tx.general + ': ' + estado(data.overall_status);
      var groups = data.groups || {};
      var html = Object.keys(groups).map(function (g) {
        return '<section class="group"><h2>' + esc(g) + '</h2>' + groups[g].map(function (c) {
          return '<div class="row"><div><div class="name">' + esc(c.name) + '</div><div class="desc">' + esc(c.description || '') +
            '</div></div><div class="status ' + esc(c.status) + '">' + esc(estado(c.status)) + '</div></div>';
        }).join('') + '</section>';
      }).join('');
      $content.innerHTML = html || '<div class="err">' + esc(tx.sin_componentes) + '</div>';
      $foot.textContent = data.generated_at ? tx.actualizado + ': ' + new Date(data.generated_at).toLocaleString(document.documentElement.lang) : '';
    })
    .catch(function (err) {
      $content.innerHTML = '<div class="err">' + esc(tx.error) + ': ' + esc(err.message) + '</div>';
      $overall.textContent = tx.no_disponible;
    });
})();
""" % json.dumps(api_v1)


def guion_del_widget(api_v1: str) -> str:
    return """(function () {
  var TEXTOS = %s;
  var script = document.currentScript;
  // La API es la de donde vino este script, no la de la web que lo incrusta.
  var base = (script && script.getAttribute('data-api-base')) || (new URL(script.src)).origin + %s;
  var target = script && script.getAttribute('data-target') ? document.querySelector(script.getAttribute('data-target')) : null;
  if (!target) { target = document.createElement('div'); script.parentNode.insertBefore(target, script.nextSibling); }
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (m) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]; }); }
  target.style.cssText = 'font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto;border:1px solid #d1d5db;border-radius:10px;padding:12px;max-width:420px';
  var org = (script && script.getAttribute('data-org')) || '';
  fetch(base + '/sd/status-page' + (org ? '?org=' + encodeURIComponent(org) : ''))
    .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
    .then(function (cuerpo) {
      var data = cuerpo.data || cuerpo, tx = TEXTOS[data.idioma] || TEXTOS.es;
      var estado = function (s) { return tx[s] || String(s || '').replace(/_/g, ' '); };
      var filas = [];
      Object.keys(data.groups || {}).forEach(function (g) {
        data.groups[g].forEach(function (c) {
          filas.push('<div style="display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-top:1px solid #eef2f7"><span>' +
            esc(c.name) + '</span><strong style="text-transform:uppercase;font-size:11px">' + esc(estado(c.status)) + '</strong></div>');
        });
      });
      target.innerHTML = '<div style="font-weight:700;margin-bottom:8px">' + esc(tx.titulo) + '</div>' +
        '<div style="font-size:12px;color:#4b5563;margin-bottom:8px">' + esc(tx.general) + ': <strong>' + esc(estado(data.overall_status)) + '</strong></div>' +
        (filas.join('') || '<div style="font-size:12px;color:#6b7280">' + esc(tx.sin_componentes) + '</div>');
    })
    .catch(function () { target.innerHTML = '<div style="color:#b91c1c;font-size:12px">' + esc((TEXTOS.es).no_disponible) + '</div>'; });
})();
""" % (json.dumps(TEXTOS), json.dumps(api_v1))
