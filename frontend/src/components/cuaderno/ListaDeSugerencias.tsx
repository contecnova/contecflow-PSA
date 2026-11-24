/**
 * Lista de candidatos de `#` (tareas, tickets, proyectos, clientes) y `@`
 * (personas) mientras se escribe. Flechas, Intro y Esc; los mismos datos que
 * las búsquedas de cada módulo (el servidor acota a lo que se puede ver).
 */
import { forwardRef, useEffect, useImperativeHandle, useState } from 'react'
import { AtSign, CheckSquare, FolderOpen, Hash, Ticket, UserCheck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Pulsable } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import type { Candidato } from '../../services/api/cuaderno'

const ICONOS: Record<string, LucideIcon> = { task: CheckSquare, ticket: Ticket, project: FolderOpen, client: UserCheck, user: AtSign }

export interface PropsDeSugerencias {
  items: Candidato[]
  command: (c: Candidato) => void
}

export interface ManejadorDeSugerencias {
  onKeyDown: (p: { event: KeyboardEvent }) => boolean
}

const ListaDeSugerencias = forwardRef<ManejadorDeSugerencias, PropsDeSugerencias>(function ListaDeSugerencias({ items, command }, ref) {
  const t = useAppT()
  const [sel, setSel] = useState(0)
  useEffect(() => setSel(0), [items])
  useImperativeHandle(ref, () => ({
    onKeyDown: ({ event }) => {
      if (!items.length) return false
      if (event.key === 'ArrowDown') { setSel(s => (s + 1) % items.length); return true }
      if (event.key === 'ArrowUp') { setSel(s => (s - 1 + items.length) % items.length); return true }
      if (event.key === 'Enter' || event.key === 'Tab') { command(items[sel]); return true }
      return false
    },
  }), [items, sel, command])

  return (
    <div className="cdn-sugerencias__lista" role="listbox" aria-label={t('cuaderno.sugerencias')}>
      {items.length === 0 && <div className="cdn-sugerencias__vacio">{t('cuaderno.sin_resultados')}</div>}
      {items.map((c, i) => {
        const Icono = ICONOS[c.type] || Hash
        return (
          <Pulsable key={`${c.type}:${c.id}`} role="option" aria-selected={i === sel}
            className={`cdn-sugerencias__item${i === sel ? ' cdn-sugerencias__item--sel' : ''}`}
            onClick={() => command(c)}>
            <Icono size={13} aria-hidden />
            <span className="cdn-sugerencias__texto">{c.label}</span>
            {(c.subtitle || c.status) && <span className="cdn-sugerencias__sub">{c.subtitle || c.status}</span>}
          </Pulsable>
        )
      })}
    </div>
  )
})

export default ListaDeSugerencias
