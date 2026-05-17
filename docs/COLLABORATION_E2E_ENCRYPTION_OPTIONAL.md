# Cifrado E2E Opcional en Collaboration (P3)

## Objetivo
Introducir cifrado end-to-end opcional por tenant/canal sin romper compatibilidad con clientes actuales.

## Principios
- Opt-in por tenant y por canal/conversacion.
- Compatibilidad progresiva: clientes legacy siguen funcionando en modo no-E2E.
- Servidor no puede leer `body` en modo E2E; solo enruta y persiste envelope.
- Mantener ABAC, auditoria y retencion sin exponer contenido.

## Modelo de rollout

### Fase 0 (actual)
- Mensajes almacenan `body` en claro y `metadata_json`.
- Existe cifrado at-rest en otros dominios (`app/core/encryption.py`) reusable para secreto de material de claves de tenant.

### Fase 1 (compat sin migracion DB)
Usar `metadata_json` de `collaboration_messages` para envelope E2E:

```json
{
  "e2ee": {
    "enabled": true,
    "v": 1,
    "alg": "x25519+aes-gcm",
    "key_id": "tenant-or-channel-key-id",
    "nonce": "base64",
    "aad": "conversation_id:message_id:sent_at",
    "ciphertext": "base64",
    "sender_device_id": "..."
  }
}
```

- `body` puede quedar nulo o con marcador (`[encrypted]`).
- `metadata_json.e2ee` permite coexistencia con mensajes no cifrados.

### Fase 2 (gestion de claves)
- Clave maestra por tenant (KMS o local cifrada con `encrypt_value`).
- Derivacion por canal/conversacion (`key_id` versionado).
- Rotacion programada y estado de salud similar a integraciones (`key_management`).

### Fase 3 (clientes)
- Handshake de capacidades al abrir conversacion (`supports_e2ee`, `key_id`, `required`).
- Envio: cliente cifra y envia envelope.
- Recepcion: cliente descifra localmente.
- Fallback: si un cliente no soporta E2E en canal `required=true`, bloquear envio con error explicito.

## Compatibilidad con cumplimiento
- Retencion/legal hold siguen operando sobre metadata temporal/estructural.
- E-discovery marca contenido como cifrado si no hay llave de descifrado autorizada.
- Auditoria conserva eventos (quien, cuando, donde) sin texto en claro.

## Riesgos y mitigaciones
- Busqueda de texto full-text no disponible en E2E: mantener indices/feature flag para canales no-E2E.
- Bot/integraciones no pueden leer contenido E2E: declarar incompatibilidad por canal o usar opt-in por bot trusted.
- Perdida de claves de dispositivo: recovery via re-wrapping con clave de tenant y politicas de recuperacion.

## Propuesta de flags
- Tenant setting: `collaboration.e2ee_enabled` (bool)
- Channel policy: `collaboration.channel.e2ee_mode` (`off|optional|required`)

## Validacion inicial recomendada
1. POC en mensajes directos internos.
2. Medir latencia y tamano de payload.
3. Verificar no regresion en retencion/auditoria/notificaciones.
