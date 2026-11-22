#!/bin/sh
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — genera la configuración de Alertmanager desde el entorno
#
# Alertmanager no expande variables de entorno en su YAML, y los destinatarios
# (correo, webhook) y la contraseña SMTP son de cada instalación: no pueden ir
# escritos en el repositorio. Este script, que es el `entrypoint` del contenedor
# (docker-compose.yml), escribe la configuración en un tmpfs (no persiste en
# disco ni en el volumen) y arranca Alertmanager con ella.
#
# Variables (todas opcionales; .env.example):
#   ALERT_WEBHOOK_URL       URL que recibe el JSON de Alertmanager (Teams/Slack vía
#                           pasarela, n8n, un endpoint propio...).
#   ALERT_EMAIL_TO          destinatario(s) del correo de alertas.
#   ALERT_EMAIL_FROM        remitente.
#   ALERT_SMTP_HOST         servidor:puerto (p. ej. smtp.office365.com:587).
#   ALERT_SMTP_USER / ALERT_SMTP_PASSWORD   credenciales SMTP.
#   ALERT_SMTP_REQUIRE_TLS  true | false (true por defecto).
# Sin webhook ni correo, las alertas se ven en la interfaz de Alertmanager y en
# Grafana, pero no se envían a nadie (receptor `solo-interfaz`).
# ══════════════════════════════════════════════════════════════════════════════
set -eu

DESTINO_DIR="${ALERTMANAGER_CONFIG_DIR:-/run/alertmanager}"
DESTINO="$DESTINO_DIR/alertmanager.yml"
mkdir -p "$DESTINO_DIR"
umask 077

# Cadena YAML entre comillas dobles, con \ y " escapados.
q() {
  printf '"%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
}

WEBHOOK="${ALERT_WEBHOOK_URL:-}"
EMAIL_TO="${ALERT_EMAIL_TO:-}"
EMAIL_FROM="${ALERT_EMAIL_FROM:-alertas@contecflow.local}"
SMTP_HOST="${ALERT_SMTP_HOST:-}"
SMTP_USER="${ALERT_SMTP_USER:-}"
SMTP_PASSWORD="${ALERT_SMTP_PASSWORD:-}"
SMTP_TLS="${ALERT_SMTP_REQUIRE_TLS:-true}"
case "$SMTP_TLS" in true|false) ;; *) SMTP_TLS=true ;; esac

RECEPTOR="solo-interfaz"
if [ -n "$WEBHOOK" ] || { [ -n "$EMAIL_TO" ] && [ -n "$SMTP_HOST" ]; }; then
  RECEPTOR="contecflow"
fi

{
  echo "# Generado por ops/alertmanager/generar-config.sh al arrancar. No editar."
  echo "global:"
  echo "  resolve_timeout: 5m"
  if [ -n "$EMAIL_TO" ] && [ -n "$SMTP_HOST" ]; then
    echo "  smtp_smarthost: $(q "$SMTP_HOST")"
    echo "  smtp_from: $(q "$EMAIL_FROM")"
    echo "  smtp_require_tls: $SMTP_TLS"
    if [ -n "$SMTP_USER" ]; then
      echo "  smtp_auth_username: $(q "$SMTP_USER")"
      echo "  smtp_auth_password: $(q "$SMTP_PASSWORD")"
    fi
  fi
  echo "route:"
  echo "  receiver: $RECEPTOR"
  echo "  group_by: [alertname, empresa]"
  echo "  group_wait: 30s"
  echo "  group_interval: 5m"
  echo "  repeat_interval: 4h"
  echo "  routes:"
  echo "    - matchers: ['severity=\"info\"']"
  echo "      receiver: $RECEPTOR"
  echo "      repeat_interval: 24h"
  echo "inhibit_rules:"
  echo "  # Con la API caída no se avisa además de cada síntoma suyo."
  echo "  - source_matchers: ['alertname=\"ApiCaida\"']"
  echo "    target_matchers: ['alertname=~\"TasaDeErrores5xxAlta|LatenciaP95Alta|ColectorDeNegocioConErrores\"']"
  echo "  - source_matchers: ['alertname=~\"PostgresCaido|RedisCaido\"']"
  echo "    target_matchers: ['alertname=~\"ApiCaida|ColaDeCeleryAtascada|TasaDeErrores5xxAlta\"']"
  echo "receivers:"
  echo "  - name: solo-interfaz"
  if [ "$RECEPTOR" = "contecflow" ]; then
    echo "  - name: contecflow"
    if [ -n "$WEBHOOK" ]; then
      echo "    webhook_configs:"
      echo "      - url: $(q "$WEBHOOK")"
      echo "        send_resolved: true"
    fi
    if [ -n "$EMAIL_TO" ] && [ -n "$SMTP_HOST" ]; then
      echo "    email_configs:"
      echo "      - to: $(q "$EMAIL_TO")"
      echo "        send_resolved: true"
    fi
  fi
} > "$DESTINO"

echo "Alertmanager: receptor '$RECEPTOR' (webhook: $([ -n "$WEBHOOK" ] && echo sí || echo no), correo: $([ -n "$EMAIL_TO" ] && [ -n "$SMTP_HOST" ] && echo sí || echo no))"

exec /bin/alertmanager \
  --config.file="$DESTINO" \
  --storage.path=/alertmanager \
  --web.listen-address=:9093 \
  --data.retention="${ALERTMANAGER_RETENTION:-120h}" \
  "$@"
