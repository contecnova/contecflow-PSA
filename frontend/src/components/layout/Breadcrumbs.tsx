import { NavLink } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

export interface BreadcrumbItem {
  label: string
  to?: string
}

interface Props {
  items?: BreadcrumbItem[]
}

export default function Breadcrumbs({ items = [] }: Props) {
  if (!items.length) return null

  return (
    <div className="app-topbar-breadcrumb" aria-label="Breadcrumb">
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1
        return (
          <span key={`${item.to || item.label}-${idx}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {isLast || !item.to ? (
              <span style={{ color: 'var(--text-1)', fontSize: "var(--text-base)", fontWeight: 600, textTransform: 'capitalize' }}>
                {item.label}
              </span>
            ) : (
              <NavLink
                to={item.to}
                style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)", textDecoration: 'none' }}
              >
                {item.label}
              </NavLink>
            )}
            {!isLast && <ChevronRight size={12} style={{ color: 'var(--text-4)', flexShrink: 0 }} />}
          </span>
        )
      })}
    </div>
  )
}
