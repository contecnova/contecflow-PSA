import { Link, useLocation } from 'react-router-dom'

export default function ForbiddenPage() {
  const location = useLocation()
  const from = location.state?.from || 'ruta desconocida'

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--surface-0)',
      color: 'var(--text-1)',
      padding: 24,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 640,
        background: 'var(--surface-1)',
        border: '1px solid var(--surface-4)',
        borderRadius: 14,
        padding: 28,
        boxShadow: '0 12px 28px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>403</div>
        <h1 style={{ margin: '0 0 10px', fontSize: 22, color: 'var(--danger)' }}>
          Acceso denegado
        </h1>
        <p style={{ margin: '0 0 8px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          No tienes permiso para acceder a esta ruta.
        </p>
        <p style={{ margin: '0 0 18px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          Ruta solicitada: <strong style={{ color: 'var(--text-1)' }}>{from}</strong>
        </p>
        <p style={{ margin: '0 0 22px', color: 'var(--text-3)', fontSize: 13 }}>
          Si crees que esto es un error, contacta con tu administrador.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link
            to="/"
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              border: 'none',
              textDecoration: 'none',
              background: 'var(--accent)',
              color: 'white',
              fontWeight: 600,
            }}
          >
            Ir al inicio
          </Link>
          <Link
            to="/imputar"
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              border: '1px solid var(--surface-4)',
              textDecoration: 'none',
              background: 'transparent',
              color: 'var(--text-1)',
              fontWeight: 600,
            }}
          >
            Ir a imputaciones
          </Link>
        </div>
      </div>
    </div>
  )
}
