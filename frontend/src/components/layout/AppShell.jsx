export default function AppShell({ children }) {
  return (
    <div className="app-main-shell" style={{ minHeight: '100vh', paddingTop: 'var(--safe-top)', paddingBottom: 'var(--safe-bottom)' }}>
      {children}
    </div>
  )
}
