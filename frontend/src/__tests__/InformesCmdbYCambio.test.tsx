/**
 * Informes de CMDB y del análisis del cambio (19-11-2026): sustituyen al
 * volcado genérico `VistaDeDatos`. Se comprueba que cada informe pinta sus
 * columnas propias, traduce los códigos, no enseña ids internos y tiene un
 * estado vacío con mensaje.
 */
import type { ReactNode } from 'react'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLangProvider } from '../i18n/AppLangContext'
import {
  InformeCandidatos, InformeDeriva, InformeEjecuciones, InformeRadioDeImpacto, InformeRetirada, InformeSaludReconciliacion,
} from '../components/cmdb/InformesDeCmdb'
import {
  InformeComunicaciones, InformeFlujoCab, InformeImpacto, InformeMatrizDeRiesgo, InformePruebas, InformeSimulacion,
  InformeVueltaAtras, tramoDeAviso,
} from '../components/servicedesk/InformesDelCambio'
import { codigo, listaDe } from '../components/servicedesk/InformesComunes'

// `useTono` lee los umbrales de /settings/org-defaults: sin servidor, los de serie.
vi.mock('../services/api', () => ({ default: { get: () => Promise.resolve({ data: {} }) } }))

beforeAll(() => {
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
const cabeceras = (c: HTMLElement) => Array.from(c.querySelectorAll('thead th')).map(th => th.textContent?.trim())
/** Ningún código interno con guion bajo a la vista. */
const sinCodigos = (c: HTMLElement, codigos: string[]) => codigos.forEach(k => expect(c.textContent ?? '').not.toContain(k))

describe('utilidades comunes', () => {
  it('codigo quita el prefijo de enumerado y listaDe acepta array o { items }', () => {
    expect(codigo('CIType.server')).toBe('server')
    expect(codigo(null)).toBe('')
    expect(listaDe([1, 2])).toEqual([1, 2])
    expect(listaDe({ items: [3] })).toEqual([3])
    expect(listaDe(null)).toEqual([])
  })
  it('tramo de un aviso del plan de comunicaciones', () => {
    expect(tramoDeAviso('T-24h')).toBe('pre_change')
    expect(tramoDeAviso('change_midpoint')).toBe('during_change')
    expect(tramoDeAviso('post_pir')).toBe('post_change')
  })
})

describe('Informes de CMDB', () => {
  it('ejecuciones: tabla con columnas propias, estado y origen traducidos, sin ids', () => {
    const { container } = montar(<InformeEjecuciones datos={[
      { id: UUID, provider_id: UUID_2, status: 'ok', started_at: '2026-11-18T10:00:00Z', finished_at: '2026-11-18T10:05:00Z',
        cis_created: 3, cis_updated: 7, cis_deactivated: 1, error_message: null, summary_json: '{"created":3}', triggered_by: 'manual' },
    ]} />)
    expect(cabeceras(container)).toEqual(['Inicio', 'Estado', 'Origen', 'Duración', 'Creados', 'Actualizados', 'Desactivados'])
    expect(screen.getByText('Correcto')).toBeInTheDocument()
    expect(screen.getByText('Manual')).toBeInTheDocument()
    expect(screen.getByText('5m')).toBeInTheDocument()
    sinUuid(container)
  })

  it('ejecuciones: vacío con mensaje (también si llega como { items })', () => {
    const { container } = montar(<InformeEjecuciones datos={{ items: [] }} />)
    expect(container.textContent).toContain('Este proveedor aún no se ha ejecutado')
  })

  it('salud de la reconciliación: KPIs traducidos y barras por proveedor', () => {
    const { container } = montar(<InformeSaludReconciliacion datos={{
      total_discovered: 10, active_discovered: 8, stale_discovered: 2, duplicate_external_ids: 1, reconciliation_score: 83,
      by_provider: { aws: { total: 6, active: 6, retired: 0 }, unknown: { total: 4, active: 2, retired: 2 } },
    }} />)
    expect(container.textContent).toContain('Salud de la reconciliación')
    expect(container.textContent).toContain('Ids externos repetidos')
    expect(container.textContent).toContain('AWS')
    expect(container.textContent).toContain('Sin proveedor')
    sinCodigos(container, ['total_discovered', 'by_provider', 'unknown'])
  })

  it('candidatos: conserva/duplicado con la confianza, sin ids', () => {
    const { container } = montar(<InformeCandidatos datos={[
      { provider: 'vsphere', confidence: 0.93,
        keeper: { id: UUID, name: 'web01', hostname: 'web01.local', ip_address: '10.0.0.1' } as never,
        duplicate: { id: UUID_2, name: 'WEB01', hostname: 'web01', ip_address: '10.0.0.1' } as never },
    ]} />)
    expect(cabeceras(container)).toEqual(['Se conserva', 'Duplicado', 'Proveedor', 'Confianza'])
    expect(screen.getByText('vSphere')).toBeInTheDocument()
    expect(container.textContent).toContain('93')
    sinUuid(container)
  })

  it('deriva: entorno traducido y cambios «antes → después»; vacío con mensaje', () => {
    const { container, unmount } = montar(<InformeDeriva datos={{ total_drifted: 1, items: [
      { ci_id: UUID, name: 'db01', ci_type: 'database', environment: 'production', provider: 'aws',
        drift_detected_at: '2026-11-19T08:00:00Z', last_discovered_at: null, ip_address: '10.0.0.5', hostname: 'db01',
        recent_changelog: [{ field: 'ip_address', old_value: '10.0.0.4', new_value: '10.0.0.5', summary: null, created_at: '2026-11-19T08:00:00Z' }] },
    ] }} />)
    expect(container.textContent).toContain('Producción')
    expect(container.textContent).toContain('Base de datos')
    expect(container.textContent).toContain('10.0.0.4 → 10.0.0.5')
    sinUuid(container)
    unmount()
    const vacio = montar(<InformeDeriva datos={{ total_drifted: 0, items: [] }} />)
    expect(vacio.container.textContent).toContain('Sin deriva en el periodo')
  })

  it('radio de impacto: KPIs y barras por criticidad traducidas', () => {
    const { container } = montar(<InformeRadioDeImpacto datos={{
      impacted_count: 5, truncated: false, criticality_breakdown: { critical: 1, high: 2, medium: 2, low: 0 },
      estimated_affected_users: 740, highest_criticality: 'critical', max_depth: 5,
    }} />)
    expect(container.textContent).toContain('CIs afectados')
    expect(container.textContent).toContain('Usuarios afectados (estimación)')
    expect(container.textContent).toContain('Crítico')
    sinCodigos(container, ['criticality_breakdown', 'estimated_affected_users'])
  })

  it('retirada: CIs y activos con sus columnas, estados traducidos y recomendaciones', () => {
    const { container } = montar(<InformeRetirada datos={{
      ci: { code: 'CI-0001', name: 'ERP', ci_type: 'application', status: 'operational', criticality: 'high' },
      summary: { risk_level: 'high', impacted_ci_count: 1, impacted_asset_count: 1, direct_impacted_ci_count: 1, max_depth: 5,
        truncated: false, highest_criticality: 'high', assets_by_status: { in_use: 1 }, assets_by_type: { laptop: 1 } },
      impacted_cis: [{ ci_id: UUID, ci_name: 'Base ERP', ci_type: 'database', criticality: 'critical', relation: 'depends_on', depth: 1 }],
      impacted_assets: [{ id: UUID_2, asset_tag: 'PT-12', name: 'Portátil Ana', type: 'laptop', status: 'in_use', assigned_to_name: 'Ana', ci_name: 'ERP' }],
    }} />)
    expect(container.textContent).toContain('Depende de')
    expect(container.textContent).toContain('Portátil')
    expect(screen.getAllByText('En uso').length).toBeGreaterThan(0)
    expect(container.textContent).toContain('Avisa a quienes usan los activos')
    sinUuid(container)
    sinCodigos(container, ['depends_on', 'in_use'])
  })
})

describe('Informes del análisis del cambio', () => {
  it('impacto: KPIs de riesgo, componentes y software de los CIs', () => {
    const { container } = montar(<InformeImpacto datos={{
      risk_score: 62, risk_label: 'high',
      risk_components: { change_type_score: 40, ci_count_score: 10, downtime_score: 5, open_tickets_penalty: 3, incident_penalty: 4 },
      affected_cis: { direct_count: 1, expanded_count: 2, critical_cis: ['ERP'],
        ci_list: [{ id: UUID, name: 'ERP', ci_type: 'CIType.application', status: 'CIStatus.operational', criticality: 'critical' }] },
      open_incidents_on_cis: 1, incidents_last_30d: 2,
      suggested_window: { day_of_week: 1, hour_utc: 2, window_label: 'Tuesday 02:00–06:00 UTC', avg_incidents_in_window: 0.25, confidence: 'low' },
      software_on_cis: { instances: [{ instance_id: UUID_2, product: 'OpenSSL', version: '1.1.1', environment: 'production', open_findings: 2, lifecycle: 'eol' }],
        open_findings: 2, critical_findings: 1, eol_instances: 1 },
    }} />)
    expect(container.textContent).toContain('62/100')
    expect(container.textContent).toContain('De dónde sale la puntuación')
    expect(container.textContent).toContain('Martes 02:00–06:00 UTC')
    expect(container.textContent).toContain('Aplicación')
    expect(container.textContent).toContain('Fin de vida')
    sinUuid(container)
    sinCodigos(container, ['CIType', 'change_type_score', 'Tuesday'])
  })

  it('matriz de riesgo: columnas propias e impacto traducido', () => {
    const { container } = montar(<InformeMatrizDeRiesgo datos={[
      { ci_id: UUID, ci_name: 'ERP', ci_type: 'application', criticality: 'critical', dependency_count: 3, recent_incidents: 1, risk_score: 12, impact_level: 'critical' },
    ]} />)
    expect(cabeceras(container)).toEqual(['CI', 'Clase', 'Criticidad', 'Dependientes', 'Incidentes 30 d', 'Puntuación', 'Impacto'])
    sinUuid(container)
  })

  it('vuelta atrás: pasos con su tiempo acumulado', () => {
    const { container } = montar(<InformeVueltaAtras datos={{
      overall_risk: 'medium', affected_ci_count: 2, total_estimated_minutes: 15,
      rollback_steps: [
        { step: 1, action: 'Detener el despliegue', responsible: 'Operaciones', estimated_minutes: 5 },
        { step: 2, action: 'Restaurar la versión', responsible: 'Equipo técnico', estimated_minutes: 10 },
      ],
    }} />)
    expect(cabeceras(container)).toEqual(['Paso', 'Acción', 'Responsable', 'Tiempo', 'Empieza'])
    expect(container.textContent).toContain('T+5 min')
    expect(container.textContent).toContain('Medio')
  })

  it('pruebas: una tabla por fase con el tipo de prueba traducido', () => {
    const { container } = montar(<InformePruebas datos={{
      risk_label: 'low', total_steps: 2, estimated_total_minutes: 25, steps: [
        { step: 1, phase: 'pre_change', test_type: 'backup', description: 'Confirmar copias', expected_result: 'Copias verificadas', estimated_minutes: 15, responsible: 'Equipo técnico', automated: false },
        { step: 2, phase: 'post_change', test_type: 'smoke', description: 'Humo', expected_result: 'Todo responde', estimated_minutes: 10, responsible: 'QA', automated: true, command: 'smoke-test' },
      ],
    }} />)
    expect(container.textContent).toContain('Antes del cambio')
    expect(container.textContent).toContain('Después del cambio')
    expect(container.textContent).toContain('Prueba de humo')
    expect(container.textContent).toContain('Automática')
    sinCodigos(container, ['pre_change', 'post_change'])
  })

  it('comunicaciones: público y momento traducidos, ventana en el idioma activo', () => {
    const { container } = montar(<InformeComunicaciones datos={{
      risk_label: 'critical', suggested_window: 'Tuesday 02:00–06:00 UTC', total_notifications: 1, notifications: [
        { id: 1, timing: 'T-7d', hours_before_change: 168, audience: 'Executive Team', channel: 'email', subject: '[CRITICAL CHANGE] CHG-1', message_template: 'Texto', responsible: 'Change Manager' },
      ],
    }} />)
    expect(cabeceras(container)).toEqual(['Cuándo', 'Público', 'Mensaje', 'Canal', 'Responsable'])
    expect(container.textContent).toContain('7 días antes')
    expect(container.textContent).toContain('Dirección')
    expect(container.textContent).toContain('Martes 02:00–06:00 UTC')
  })

  it('simulación: original frente a simulado y cambio de nivel traducido', () => {
    const lado = (score: number, risk_label: string) => ({
      score, risk_label, ci_count_expanded: 2, window: { day_of_week: 0, hour_utc: 3 },
      components: { change_type_score: score - 10, ci_count_score: 10, downtime_score: 0, open_tickets_penalty: 0, incident_penalty: 0 },
    })
    const { container } = montar(<InformeSimulacion datos={{
      original: lado(40, 'medium'), simulated: lado(80, 'critical'),
      delta: { score_diff: 40, risk_change: 'escalated', ci_count_diff: 0, window_changed: false },
    }} />)
    expect(cabeceras(container)).toEqual(['Concepto', 'Original', 'Simulado'])
    expect(container.textContent).toContain('Sube')
    expect(container.textContent).toContain('+40')
    sinCodigos(container, ['escalated', 'risk_change'])
  })

  it('flujo del CAB: fase, votos traducidos y sin ids', () => {
    const { container } = montar(<InformeFlujoCab datos={{
      status: 'cab', quorum: 2, meeting: { scheduled_at: '2026-11-25T10:00:00Z', agenda: 'Revisión' },
      votes: [
        { user_id: UUID, name: 'Marta', approved: true, decision: 'approved', note: null, voted_at: '2026-11-19T09:00:00Z' },
        { user_id: UUID_2, name: 'Luis', approved: false, decision: 'pending', note: null, voted_at: null },
      ],
    }} />)
    expect(container.textContent).toContain('En el CAB')
    expect(container.textContent).toContain('Aprobado')
    expect(container.textContent).toContain('Quórum: 2')
    sinUuid(container)
  })
})
