import type { ReactNode } from 'react'

interface Props {
  children?: ReactNode
}

export default function AppShell({ children }: Props) {
  return (
    <div className="app-main-shell" style={{ minHeight: '100vh', paddingTop: 'var(--safe-top)', paddingBottom: 'var(--safe-bottom)' }}>
      {children}
    </div>
  )
}
