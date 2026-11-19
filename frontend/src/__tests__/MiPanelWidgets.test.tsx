/**
 * Mi panel (19-11-2026): cada widget con su render propio, como los informes
 * del sistema. Se comprueba lo que hacía mal el volcado genérico: nada de ids
 * internos a la vista, etiquetas traducidas (no «Sla at risk count»), tablas
 * con sus columnas, estados vacíos con mensaje y clic que abre el ticket.
 */
import type { ReactNode } from 'react'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLangProvider } from '../i18n/AppLangContext'
import {
  TAMANO_DE_WIDGET, WidgetAgenteAutonomo, WidgetCab, WidgetIncidentesMayores, WidgetMetricasItil, WidgetMiCola,
  WidgetMisAprobaciones, WidgetRendimiento, WidgetRiesgoSla, variacion,
} from '../components/servicedesk/WidgetsDelPanel'
import VistaDeDatos, { limpiarDatos } from '../components/servicedesk/VistaDeDatos'

// `useTono` lee los umbrales de /settings/org-defaults: sin servidor, los de serie.
vi.mock('../services/api', () => ({ default: { get: () => Promise.resolve({ data: {} }) } }))

beforeAll(() => {
  // Recharts (ResponsiveContainer) necesita ResizeObserver; jsdom no lo trae.
  if (!('ResizeObserver' in globalThis)) {
    (globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  }
})

const UUID = '3f2b8c1e-9a4d-4e2f-8b7a-1c2d3e4f5a6b'
const UUID_2 = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'

function montar(nodo: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><AppLangProvider>{nodo}</AppLangProvider></QueryClientProvider>)
}
const sinUuid = (c: HTMLElement) => expect(c.textContent ?? '').not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i)
const cabeceras = (c: HTMLElement) => Array.from(c.querySelectorAll('th')).map(th => th.textContent?.trim())

describe('Mi panel — renders por widget', () => {
  it('incidentes mayores: tabla con columnas útiles, estado traducido y sin el UUID', () => {
    const { container } = montar(<WidgetIncidentesMayores onAbrir={() => {}} datos={[
      { id: UUID, number: 'MI0007', title: 'Caída del ERP', status: 'active', severity: 'P1', declared_at: '2026-11-18T09:30:00+00:00', resolved_at: null, commander: 'Ana Ruiz', impact_statement: 'Sin facturación' },
    ]} />)
    expect(cabeceras(container)).toEqual(['Incidente', 'Severidad', 'Estado', 'Declarado', 'Responsable'])
    expect(screen.getByText('MI0007')).toBeInTheDocument()
    expect(screen.getByText('Caída del ERP')).toBeInTheDocument()
    expect(screen.getByText('Activo')).toBeInTheDocument()
    expect(screen.getByText('Ana Ruiz')).toBeInTheDocument()
    sinUuid(container)
  })

  it('riesgo de SLA: KPIs con etiquetas traducidas, nunca las claves técnicas', () => {
    const { container } = montar(<WidgetRiesgoSla onAbrir={() => {}} datos={{
      open_tickets: 40, severity_distribution: { critical: 2, high: 5, medium: 10, low: 3 },
      sla_at_risk_count: 6, sla_at_risk_pct: 30, analyzed_tickets: 20, truncated: true, failed_tickets: 0,
    }} />)
    const texto = container.textContent ?? ''
    expect(texto).toContain('En riesgo de SLA')
    expect(texto).toContain('Severidad prevista')
    expect(texto).toContain('Crítica')
    expect(texto).not.toMatch(/Sla at risk|Analyzed tickets|Recortado|sla_at_risk|severity_distribution/)
  })

  it('mis aprobaciones: vacío con mensaje (no «—») y, con datos, clic que abre el ticket', () => {
    const vacio = montar(<WidgetMisAprobaciones onAbrir={() => {}} datos={[]} />)
    expect(vacio.container.textContent).toContain('Nada pendiente de tu aprobación')
    expect(vacio.container.textContent?.trim()).not.toBe('—')
    vacio.unmount()

    const onAbrir = vi.fn()
    const { container } = montar(<WidgetMisAprobaciones onAbrir={onAbrir} datos={[
      { approval_id: UUID, ticket_id: UUID_2, number: 'REQ-0042', title: 'Portátil nuevo', requester_name: 'Luis Gil', service_item_name: 'Hardware', created_at: '2026-11-19T08:00:00+00:00' },
    ]} />)
    expect(cabeceras(container)).toEqual(['Petición', 'Solicitante', 'Esperando'])
    fireEvent.click(screen.getByText('Portátil nuevo'))
    expect(onAbrir).toHaveBeenCalledWith(UUID_2)
    sinUuid(container)
  })

  it('mi cola: número, título, estado y prioridad traducidos; abre el ticket', () => {
    const onAbrir = vi.fn()
    const { container } = montar(<WidgetMiCola onAbrir={onAbrir} datos={[
      { id: UUID, number: 'INC-0100', title: 'VPN no conecta', status: 'in_progress', priority: 'p2_high', priority_score: 0.82, sla_resolution_due: null },
    ]} />)
    expect(cabeceras(container)).toEqual(['Ticket', 'Estado', 'Prioridad', 'Vence el SLA', 'Urgencia'])
    expect(screen.getByText('En curso')).toBeInTheDocument()
    expect(screen.getByText('P2 Alta')).toBeInTheDocument()
    fireEvent.click(screen.getByText('VPN no conecta'))
    expect(onAbrir).toHaveBeenCalledWith(UUID)
    sinUuid(container)
  })

  it('CAB: tipo y estado del cambio traducidos, riesgo con puntuación', () => {
    const { container } = montar(<WidgetCab onAbrir={() => {}} datos={{ total: 1, unscored: 0, items: [
      { id: UUID, number: 'CHG-0009', title: 'Parche del kernel', change_type: 'normal', status: 'cab_review', risk: 'high', planned_start: '2026-11-25 22:00:00', owner: 'Marta', requester: null, auto_risk_score: 81, auto_risk_label: 'high' },
    ] }} />)
    expect(cabeceras(container)).toEqual(['Cambio', 'Tipo', 'Riesgo', 'Estado', 'Inicio previsto', 'Responsable'])
    expect(screen.getByText('En revisión del CAB')).toBeInTheDocument()
    expect(container.textContent).toContain('81')
    sinUuid(container)
  })

  it('rendimiento: solo agentes con tickets, columnas traducidas', () => {
    const { container } = montar(<WidgetRendimiento onAbrir={() => {}} datos={[
      { agent_id: UUID, agent_name: 'Pilar', total: 10, resolved: 8, open: 2, mttr_minutes: 95, avg_csat: 4.5, sla_breaches: 1 },
      { agent_id: UUID_2, agent_name: 'Sin tickets', total: 0, resolved: 0, open: 0, mttr_minutes: null, avg_csat: null, sla_breaches: 0 },
    ]} />)
    expect(cabeceras(container)).toEqual(['Agente', 'Tickets', 'Resolución', 'MTTR', 'CSAT', 'Incumplimientos SLA'])
    expect(screen.queryByText('Sin tickets')).not.toBeInTheDocument()
    expect(screen.getAllByText('1h 35m').length).toBeGreaterThan(0)
    sinUuid(container)
  })

  it('métricas ITIL y agente autónomo: KPIs traducidos y vacíos con mensaje', () => {
    const itil = montar(<WidgetMetricasItil onAbrir={() => {}} datos={{
      volume: { total: 50, open: 10, resolved: 40, breached_sla: 3 }, sla_compliance_pct: 92.5, mttr_minutes: 120,
      fcr_percent: 70, avg_csat: 4.2, by_type: { incident: 30, request: 20 }, by_priority: { p1_critical: 5, p3_medium: 45 }, breach_by_priority: {},
    }} previo={{ volume: { total: 40, open: 0, resolved: 30, breached_sla: 1 }, sla_compliance_pct: 90 }} />)
    expect(itil.container.textContent).toContain('Cumplimiento del SLA')
    expect(itil.container.textContent).toContain('+25 % vs. 30 días anteriores')
    itil.unmount()

    const agente = montar(<WidgetAgenteAutonomo onAbrir={() => {}} datos={{
      total_executions: 0, success: 0, applied: 0, suggested: 0, discarded: 0, skipped: 0, failed: 0, success_rate_pct: 0, by_playbook_type: {},
    }} />)
    expect(agente.container.textContent).toContain('El agente autónomo aún no ha actuado')
  })

  it('tamaños: KPIs compactos y tablas anchas', () => {
    expect(TAMANO_DE_WIDGET.sla_risk).toBe(4)
    expect(TAMANO_DE_WIDGET.major_incidents).toBe(8)
    expect(TAMANO_DE_WIDGET.itil_metrics).toBe(12)
    expect(variacion(50, 40)).toBe(25)
    expect(variacion(5, 0)).toBeNull()
  })
})

describe('VistaDeDatos — sin ids internos', () => {
  it('quita claves de id y valores con forma de UUID, y abre JSON en texto', () => {
    expect(limpiarDatos({ id: UUID, ci_id: 'x', name: 'web01', owner: UUID, summary_json: '{"created": 2}' }))
      .toEqual({ name: 'web01', summary_json: { created: 2 } })
  })

  it('no pinta el UUID y traduce la clave', () => {
    const { container } = montar(<VistaDeDatos datos={[{ id: UUID, number: 'MI0001', status: 'active' }]} />)
    sinUuid(container)
    expect(container.textContent).toContain('Activo')
  })
})
