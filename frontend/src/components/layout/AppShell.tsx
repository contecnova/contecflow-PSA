import type { ReactNode } from 'react'
import './AppShell.css'

interface Props {
  children?: ReactNode
}

export default function AppShell({ children }: Props) {
  return (
    <div className="app-main-shell appshel-box-1">
      {children}
    </div>
  )
}
