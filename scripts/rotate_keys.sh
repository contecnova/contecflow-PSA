#!/bin/bash
# Rotación automatizada de claves y secretos para Contecflow PSA
# Uso: bash scripts/rotate_keys.sh

set -e

# 1. Generar nueva clave secreta (por ejemplo, para JWT)
NEW_SECRET=$(openssl rand -hex 32)
echo "Nueva clave generada: $NEW_SECRET"

# 2. Actualizar .env (si existe)
if [ -f .env ]; then
  sed -i.bak "/^SECRET_KEY=/c\SECRET_KEY=$NEW_SECRET" .env
  echo ".env actualizado con nueva clave. Backup en .env.bak"
else
  echo "No se encontró .env. Por favor, actualiza manualmente tu configuración."
fi

# 3. Recordatorio para actualizar otros orígenes seguros
cat <<EOF

Recuerda actualizar también:
- Azure Key Vault, AWS Secrets Manager o el gestor de secretos que uses
- GitHub Actions Secrets (si aplica)
- Variables de entorno en servidores de producción
- Webhooks y claves de integraciones externas

Reinicia los servicios para que la nueva clave tenga efecto.
EOF
