import { Link, useLocation } from 'react-router-dom'

export default function NotFoundPage() {
  const location = useLocation()

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
        <div style={{ fontSize: "var(--text-4xl)", marginBottom: 8 }}>404</div>
        <h1 style={{ margin: '0 0 10px', fontSize: "var(--text-xl-em)", color: 'var(--warning)' }}>
          Página no encontrada
        </h1>
        <p style={{ margin: '0 0 8px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          La URL que intentaste abrir no existe o ya no está disponible.
        </p>
        <p style={{ margin: '0 0 18px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          Ruta solicitada: <strong style={{ color: 'var(--text-1)' }}>{location.pathname}</strong>
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
            Volver al inicio
          </Link>
          <Link
            to="/tasks"
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
            Ir a tareas
          </Link>
        </div>
      </div>
    </div>
  )
}
