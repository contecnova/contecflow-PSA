// Licencias y hardware — fases 1 y 3 (16-11-2026): rutas de la API, traducción
// de errores, cierre de asignaciones (revocar exige motivo) y decisión de renovación.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const { http } = vi.hoisted(() => ({ http: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

vi.mock('../services/api/_core', () => ({ default: http }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (k: string, p?: unknown) => (typeof p === 'string' ? p : k),
}))

import { almApi } from '../services/api/alm'
import type { Asignacion, Renovacion } from '../services/api/alm'
import { errorAlm, hoyIso, textoDeChecklist } from '../components/alm/almFases'
import CerrarAsignacionModal from '../components/alm/CerrarAsignacionModal'
import RenovacionesTab from '../pages/alm/RenovacionesTab'

const t = (k: string, p?: unknown) => (typeof p === 'string' && !k.startsWith('alm.err_') ? p : k)

function envolver(nodo: ReactNode) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{nodo}</QueryClientProvider>
    </MemoryRouter>,
  )
}

const asignacion = (cambios: Partial<Asignacion> = {}): Asignacion => ({
  id: 'as1', resource_type: 'license', license_id: 'l1', asset_id: null, resource_name: 'M365 E3',
  holder_type: 'user', holder_id: 'u1', holder_name: 'Ana', mode: 'assignment', parent_id: null, quantity: 1,
  status: 'active', valid_from: '2026-11-01', valid_to: null, ended_on: null, end_kind: null, end_reason: null,
  reason: null, source: 'manual', assigned_by: null, assigned_by_name: null, assigned_at: null, approved_at: null,
  charge_project_id: null, charge_cost_center_id: null, charge_client_id: null, rebillable: null, notes: null,
  used_in_pool: null, overdue: false, days_to_due: null, ...cambios,
})

describe('rutas de la API de las fases 1 y 3', () => {
  beforeEach(() => Object.values(http).forEach(f => f.mockReset().mockResolvedValue({ data: {} })))

  it('asignar, cerrar, devolver, historial, costes, renovaciones y facturas', async () => {
    await almApi.asignarLicencia('l1', { holder_type: 'project', holder_id: 'p1', quantity: 5, mode: 'pool' })
    await almApi.cerrar('as1', 'revoked', 'Ya no lo necesita')
    await almApi.devolver('as2', { condition: 'fair', to_repair: true })
    await almApi.historial({ holder_type: 'user', holder_id: 'u1' })
    await almApi.costes({ from: '2026-11-01', to: '2026-11-30', group_by: 'project' })
    await almApi.decidir({ entity_type: 'contract', entity_id: 'c1', decision: 'cancel', reason: 'Sin uso' })
    await almApi.enlazarGasto('f1', 'g1')
    await almApi.ciclo('a1', 'retired', 'viejo', { reason: 'obsolete' })
    expect(http.post).toHaveBeenCalledWith('/alm/licenses/l1/assign', { holder_type: 'project', holder_id: 'p1', quantity: 5, mode: 'pool' })
    expect(http.post).toHaveBeenCalledWith('/alm/assignments/as1/end', { kind: 'revoked', reason: 'Ya no lo necesita' })
    expect(http.post).toHaveBeenCalledWith('/alm/assignments/as2/return', { condition: 'fair', to_repair: true })
    expect(http.get).toHaveBeenCalledWith('/alm/history', { params: { holder_type: 'user', holder_id: 'u1' } })
    expect(http.get).toHaveBeenCalledWith('/alm/costs', { params: { from: '2026-11-01', to: '2026-11-30', group_by: 'project' } })
    expect(http.post).toHaveBeenCalledWith('/alm/renewals', { entity_type: 'contract', entity_id: 'c1', decision: 'cancel', reason: 'Sin uso' })
    expect(http.post).toHaveBeenCalledWith('/alm/invoices/f1/expense', { expense_id: 'g1' })
    expect(http.post).toHaveBeenCalledWith('/alm/assets/a1/lifecycle', { action: 'retired', reason: 'viejo', data: { reason: 'obsolete' } })
  })

  it('las listas paginadas devuelven items y total (meta.total)', async () => {
    http.get.mockResolvedValueOnce({ data: [{ id: 'x' }], meta: { total: 7 } })
    const r = await almApi.asignaciones({ page: 1 })
    expect(r).toEqual({ items: [{ id: 'x' }], total: 7 })
  })
})

describe('errorAlm', () => {
  const error = (detail: string) => ({ response: { data: { detail } } })
  it('traduce los códigos alm_* (con campo) y deja pasar el texto libre', () => {
    expect(errorAlm(t, error('alm_sin_asientos'))).toBe('alm.err_sin_asientos')
    expect(errorAlm(t, error('alm_fecha_invalida:valid_to'))).toBe('alm.err_fecha_invalida (valid_to)')
    expect(errorAlm(t, error('Otra cosa'))).toBe('Otra cosa')
    expect(errorAlm(t, {})).toBe('alm.err_generic')
  })
  it('el checklist traduce los códigos conocidos y enseña los añadidos a mano', () => {
    expect(textoDeChecklist(t, 'charger')).toBe('charger')
    expect(hoyIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('CerrarAsignacionModal', () => {
  beforeEach(() => Object.values(http).forEach(f => f.mockReset().mockResolvedValue({ data: {} })))

  it('revocar sin motivo no llama a la API; con motivo, sí', async () => {
    envolver(<CerrarAsignacionModal asignacion={asignacion()} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('radio', { name: 'alm.end_revoked' }))
    fireEvent.click(screen.getByRole('button', { name: 'alm.end_revoked_confirm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('alm.err_motivo_obligatorio')
    expect(http.post).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText(/alm.reason/), { target: { value: 'Cambio de puesto' } })
    fireEvent.click(screen.getByRole('button', { name: 'alm.end_revoked_confirm' }))
    await waitFor(() => expect(http.post).toHaveBeenCalledWith('/alm/assignments/as1/end', { kind: 'revoked', reason: 'Cambio de puesto' }))
  })

  it('un activo prestado se devuelve con el acta (por defecto)', async () => {
    http.get.mockResolvedValue({ data: { checklist: ['charger'], acts_enabled: true, loan_default_days: 14, rebill_markup_pct: 0, esign_provider: 'manual' } })
    envolver(<CerrarAsignacionModal asignacion={asignacion({ resource_type: 'asset', asset_id: 'a1', license_id: null, mode: 'loan' })} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'alm.end_return_confirm' }))
    await waitFor(() => expect(http.post).toHaveBeenCalledWith('/alm/assignments/as1/return', expect.objectContaining({ to_repair: false })))
  })
})

describe('RenovacionesTab', () => {
  const r: Renovacion = {
    entity_type: 'contract', id: 'c1', name: 'Enterprise Agreement', vendor_name: 'Microsoft', renewal_date: '2026-12-31',
    notice_days: 30, notice_deadline: '2026-12-01', days_to_renewal: 45, days_to_deadline: 15, auto_renew: true,
    annual_cost: 18600, total_seats: null, billing_cycle: 'annual', owner_id: null, decision: null, usage: null,
  }
  beforeEach(() => Object.values(http).forEach(f => f.mockReset()))

  it('lista la renovación y cancelar exige motivo', async () => {
    http.get.mockResolvedValue({ data: [r] })
    http.post.mockResolvedValue({ data: r })
    envolver(<RenovacionesTab />)
    expect(await screen.findByText('Enterprise Agreement')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'alm.decision_take' }))
    fireEvent.click(screen.getByRole('radio', { name: 'alm.decision_cancel' }))
    fireEvent.change(screen.getByLabelText(/alm.reason/), { target: { value: 'No se usa' } })
    fireEvent.click(screen.getByRole('button', { name: 'alm.decision_save' }))
    await waitFor(() => expect(http.post).toHaveBeenCalledWith('/alm/renewals', expect.objectContaining({ decision: 'cancel', reason: 'No se usa', entity_id: 'c1' })))
  })
})
