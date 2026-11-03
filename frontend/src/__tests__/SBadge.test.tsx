// Auditoría 2026-11: el estado del ticket se pintaba como código («pending third»).
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => `«${k}»` }))

import { SBadge } from '../pages/service-desk/sdUtils'

describe('SBadge', () => {
  it('traduce cada estado conocido', () => {
    for (const [estado, clave] of [['pending_third', 'status_pending_third'], ['in_progress', 'status_in_progress'],
      ['pending_client', 'status_waiting_client'], ['resolved', 'status_resolved']]) {
      const { unmount } = render(<SBadge v={estado} />)
      expect(screen.getByText(`«service_desk.${clave}»`)).toBeTruthy()
      unmount()
    }
  })
  it('un estado desconocido se ve legible, sin guiones bajos', () => {
    render(<SBadge v="on_hold" />)
    expect(screen.getByText('on hold')).toBeTruthy()
  })
})

describe('PRIORITY_LABEL', () => {
  it('se lee en el idioma activo, no en español fijo', async () => {
    const { PRIORITY_LABEL } = await import('../pages/service-desk/sdUtils')
    localStorage.setItem('contecflow_operator_lang', 'en')
    expect(PRIORITY_LABEL.p1_critical).toBe('P1 Critical')
    localStorage.setItem('contecflow_operator_lang', 'es')
    expect(PRIORITY_LABEL.p1_critical).toBe('P1 Crítico')
    expect(Object.keys(PRIORITY_LABEL)).toEqual(['p1_critical', 'p2_high', 'p3_medium', 'p4_low'])
  })
})

describe('etiquetaSd', () => {
  it('traduce los códigos de cambios, problemas e incidencias mayores', async () => {
    const { etiquetaSd } = await import('../pages/service-desk/sdUtils')
    localStorage.setItem('contecflow_operator_lang', 'es')
    expect(etiquetaSd('chg_st', 'cab_review')).toBe('En revisión del CAB')
    expect(etiquetaSd('prb_st', 'known_error')).toBe('Error conocido')
    expect(etiquetaSd('type', 'service_request')).toBe('Solicitud de servicio')
    expect(etiquetaSd('mi_st', null)).toBe('—')
  })
})
