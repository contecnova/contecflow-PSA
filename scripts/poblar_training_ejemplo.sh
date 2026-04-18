#!/bin/bash
# Script para poblar cursos, inscripciones y certificaciones de ejemplo en Contecflow-PSA
# Requiere: jq, curl, acceso a la API en localhost:8000

set -e

API_URL="http://localhost:8000/api/v1"
ADMIN_USER="admin"
ADMIN_PASS="Admin2026!"

# 1. Obtener token de admin
ADMIN_TOKEN=$(curl -s -X POST "$API_URL/auth/login" -H 'Content-Type: application/json' -d '{"username": "'$ADMIN_USER'", "password": "'$ADMIN_PASS'"}' | jq -r '.access_token')
if [[ -z "$ADMIN_TOKEN" || "$ADMIN_TOKEN" == "null" ]]; then
  echo "Error: No se pudo obtener el token de admin."
  exit 1
fi

# 2. Crear cursos de ejemplo
declare -A COURSE_IDS
for row in \
  '{"title": "Python Avanzado", "provider": "Udemy", "category": "técnico", "duration_h": 20, "cost": 29.99}' \
  '{"title": "Gestión de Proyectos", "provider": "Coursera", "category": "soft", "duration_h": 15, "cost": 0}' \
  '{"title": "Inglés Profesional", "provider": "Interno", "category": "idioma", "duration_h": 40, "cost": 0}'
do
  title=$(echo $row | jq -r .title)
  id=$(curl -s -X POST "$API_URL/training/courses" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d "$row" | jq -r '.id')
  if [[ "$id" == "null" || -z "$id" ]]; then
    # Puede que ya exista, buscarlo
    id=$(curl -s -X GET "$API_URL/training/courses" -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r ".[] | select(.title==\"$title\") | .id" | head -1)
  fi
  COURSE_IDS["$title"]=$id
done

# 3. Obtener IDs de usuarios de ejemplo
declare -A USER_IDS
for username in dev_test hr_test manager_test; do
  id=$(curl -s -X GET "$API_URL/users?search=$username" -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[0].id')
  if [[ "$id" == "null" || -z "$id" ]]; then
    echo "Usuario $username no encontrado."
    exit 1
  fi
  USER_IDS[$username]=$id
done

# 4. Inscribir usuarios a cursos
declare -A ENROLLMENTS
curl -s -X POST "$API_URL/training/enrollments" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"course_id": "'${COURSE_IDS["Python Avanzado"]}'", "user_id": "'${USER_IDS[dev_test]}'", "status": "planned"}'

curl -s -X POST "$API_URL/training/enrollments" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"course_id": "'${COURSE_IDS["Gestión de Proyectos"]}'", "user_id": "'${USER_IDS[hr_test]}'", "status": "in_progress"}'

curl -s -X POST "$API_URL/training/enrollments" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"course_id": "'${COURSE_IDS["Inglés Profesional"]}'", "user_id": "'${USER_IDS[manager_test]}'", "status": "completed"}'

# 5. Crear certificaciones para cada usuario
curl -s -X POST "$API_URL/training/certifications" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"user_id": "'${USER_IDS[dev_test]}'", "name": "AWS Certified Developer", "issuer": "Amazon", "obtained_at": "2024-01-15", "expires_at": "2027-01-15"}'

curl -s -X POST "$API_URL/training/certifications" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"user_id": "'${USER_IDS[hr_test]}'", "name": "PMP", "issuer": "PMI", "obtained_at": "2023-06-01", "expires_at": "2026-06-01"}'

curl -s -X POST "$API_URL/training/certifications" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"user_id": "'${USER_IDS[manager_test]}'", "name": "Cambridge C1", "issuer": "Cambridge", "obtained_at": "2022-09-01", "expires_at": "2027-09-01"}'

# 6. Mostrar resumen
echo "\nCursos:" && curl -s -X GET "$API_URL/training/courses" -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'
echo "\nInscripciones:" && curl -s -X GET "$API_URL/training/enrollments" -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'
echo "\nCertificaciones:" && curl -s -X GET "$API_URL/training/certifications" -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'

echo "\nPoblado de ejemplo completado."
