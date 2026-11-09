"""Widget de solicitudes para la web de un cliente (revisión 2026-11).

Antes (`/widget/ticket.js`) pedía `data-client-token`: el token del portal de
un cliente puesto en el código de una página pública, con el que cualquiera
que la abriera podía actuar como ese cliente en el portal. Además no se podía
cargar desde otro origen (`Cross-Origin-Resource-Policy: same-origin`).

Ahora usa el token de un **formulario público** (Formularios públicos), que
sólo sirve para enviar ese formulario —con su límite por minuto— y no da acceso
a nada más. La web lo pega así:

    <script src="https://<contecflow>/widget/ticket.js" data-form="<token>"></script>
"""
from __future__ import annotations

import json

TEXTOS = {
    "es": {"titulo": "Abrir una solicitud", "nombre": "Nombre", "correo": "Correo", "asunto": "Asunto",
           "descripcion": "Descripción", "enviar": "Enviar", "enviando": "Enviando…",
           "gracias": "¡Gracias! Tu solicitud ha sido enviada.", "error": "No se pudo enviar. Inténtalo de nuevo.",
           "no_disponible": "El formulario no está disponible."},
    "en": {"titulo": "Open a request", "nombre": "Name", "correo": "Email", "asunto": "Subject",
           "descripcion": "Description", "enviar": "Send", "enviando": "Sending…",
           "gracias": "Thank you! Your request has been sent.", "error": "Could not send it. Please try again.",
           "no_disponible": "The form is not available."},
    "zh": {"titulo": "提交请求", "nombre": "姓名", "correo": "邮箱", "asunto": "主题",
           "descripcion": "描述", "enviar": "提交", "enviando": "正在提交…",
           "gracias": "谢谢！你的请求已提交。", "error": "提交失败，请重试。",
           "no_disponible": "表单不可用。"},
}


def guion(api_v1: str) -> str:
    return """(function () {
  var TEXTOS = %s;
  var s = document.currentScript;
  var token = s && s.getAttribute('data-form');
  if (!token) { console.error('Contecflow: falta data-form (token del formulario público)'); return; }
  // La API es la de donde vino este script, no la de la web que lo incrusta.
  var base = (s.getAttribute('data-api-base') || (new URL(s.src)).origin + %s) + '/forms/public/' + encodeURIComponent(token);
  var caja = s.getAttribute('data-target') ? document.querySelector(s.getAttribute('data-target')) : null;
  if (!caja) { caja = document.createElement('div'); s.parentNode.insertBefore(caja, s.nextSibling); }
  caja.style.cssText = 'font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto;border:1px solid #d1d5db;border-radius:10px;padding:14px;max-width:420px;box-sizing:border-box';
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (m) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]; }); }
  var campo = 'display:block;width:100%%;box-sizing:border-box;margin:4px 0 10px;padding:8px;border:1px solid #d1d5db;border-radius:6px;font:inherit';
  fetch(base).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); }).then(function (f) {
    var tx = TEXTOS[f.idioma] || TEXTOS.es;
    caja.innerHTML = '<div style="font-weight:700;margin-bottom:8px">' + esc(f.name || tx.titulo) + '</div>' +
      (f.description ? '<div style="font-size:13px;color:#4b5563;margin-bottom:8px">' + esc(f.description) + '</div>' : '') +
      '<form><label style="font-size:12px">' + esc(tx.nombre) + '<input name="n" style="' + campo + '"></label>' +
      '<label style="font-size:12px">' + esc(tx.correo) + '<input name="e" type="email" style="' + campo + '"></label>' +
      '<label style="font-size:12px">' + esc(tx.asunto) + '<input name="a" required maxlength="200" style="' + campo + '"></label>' +
      '<label style="font-size:12px">' + esc(tx.descripcion) + '<textarea name="d" rows="4" style="' + campo + '"></textarea></label>' +
      '<button type="submit" style="padding:8px 14px;border:0;border-radius:6px;background:#111827;color:#fff;font:inherit;cursor:pointer">' + esc(tx.enviar) + '</button>' +
      '<div data-estado style="font-size:12px;margin-top:8px"></div></form>';
    var form = caja.querySelector('form'), estado = caja.querySelector('[data-estado]'), boton = form.querySelector('button');
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); boton.disabled = true; boton.textContent = tx.enviando; estado.textContent = '';
      var cuerpo = { subject: form.a.value, description: form.d.value || null,
                     submitter_name: form.n.value || null, submitter_email: form.e.value || null };
      fetch(base + '/submit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(function (res) { caja.innerHTML = '<div style="font-size:14px">' + esc(res.message || tx.gracias) + '</div>'; })
        .catch(function () { boton.disabled = false; boton.textContent = tx.enviar; estado.style.color = '#b91c1c'; estado.textContent = tx.error; });
    });
  }).catch(function () { caja.innerHTML = '<div style="font-size:12px;color:#b91c1c">' + esc(TEXTOS.es.no_disponible) + '</div>'; });
})();
""" % (json.dumps(TEXTOS), json.dumps(api_v1))
