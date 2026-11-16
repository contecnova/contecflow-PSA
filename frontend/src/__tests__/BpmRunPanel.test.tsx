// Auditoría 2026-11: /bpm no ejecutaba nada. La bandeja enseña los pasos
// humanos pendientes y completarlos manda las variables al motor.
// Revisión BPM 2026-11-16: decisiones manuales (se elige la salida), textos
// traducidos desde códigos y cancelar solo para admin/PM.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const complete = vi.fn((..._a: unknown[]) => Promise.resolve({ data: {} }))
const cancel = vi.fn(() => Promise.resolve({ data: {} }))
let bandeja: unknown[] = []
let rolesDelUsuario: string[] = ['pm']

vi.mock('../services/api', () => ({
  apiErrorMsg: () => 'error',
  bpmnInstancesApi: {
    inbox: () => Promise.resolve({ data: bandeja }),
    list: () => Promise.resolve({ data: [
      { id: 'i1', process_name: 'Compras', status: 'running', active_steps: ['Revisar solicitud'], started_at: '2026-11-04T10:00:00Z' },
    ] }),
    get: () => Promise.resolve({ data: {
      id: 'i1', status: 'failed', version: 2, error: 'texto del backend', error_code: 'no_route', error_params: { element: 'Importe' },
      steps: [{ id: 'p1', element_id: 'R', element_type: 'userTask', name: 'Revisar', status: 'completed', candidate_role: 'hr', created_at: '2026-11-04T10:00:00Z' }],
    } }),
    cancel: () => cancel(),
    complete: (...a: unknown[]) => complete(...a),
  },
}))
// Las claves de códigos (tipo, rol, motivo) se «traducen» entre corchetes; el
// resto devuelve la clave, que es lo que hace `t` cuando falta un texto.
const TRADUCIDAS = /^bpm\.(tipo|rol|error)_/
vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({
    t: (k: string, p?: Record<string, unknown>) =>
      TRADUCIDAS.test(k) ? `[${k}${p && 'element' in p ? `:${String(p.element)}` : ''}]` : k,
  }),
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ hasRole: (...r: string[]) => r.some(x => rolesDelUsuario.includes(x)) }) }))
vi.mock('../context/ConfirmContext', () => ({ useConfirm: () => ({ confirmar: () => Promise.resolve(true) }) }))

import BpmRunPanel, { BpmInbox } from '../pages/bpm/BpmRunPanel'

function montar(ui: JSX.Element) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {ui}
    </QueryClientProvider>,
  )
}

describe('BpmRunPanel', () => {
  beforeEach(() => {
    complete.mockClear()
    rolesDelUsuario = ['pm']
    bandeja = [
      { id: 's1', instance_id: 'i1', element_id: 'Revisar', name: 'Revisar solicitud', candidate_role: 'pm',
        wait_kind: 'task', process_name: 'Compras', variables: { importe: 500 }, created_at: '2026-11-04T10:00:00Z' },
    ]
  })

  it('completa un paso de la bandeja con las variables escritas', async () => {
    montar(<BpmRunPanel />)
    // El paso sale en la bandeja y en «pendiente» de la instancia; las dos listas
    // cargan por separado, así que se espera a ambas (findAll resolvía con la primera).
    await waitFor(() => expect(screen.getAllByText('Revisar solicitud')).toHaveLength(2))
    fireEvent.click(screen.getAllByText('bpm.completar')[0])
    fireEvent.change(await screen.findByLabelText('bpm.variables_ayuda'), { target: { value: 'aprobada=true\nimporte=900' } })
    fireEvent.click(screen.getAllByText('bpm.completar').at(-1)!)
    await waitFor(() => expect(complete).toHaveBeenCalledWith('i1', 's1', { variables: { aprobada: true, importe: 900 } }))
  })

  it('en una decisión obliga a elegir la salida y la manda como flow_id', async () => {
    bandeja = [
      { id: 's2', instance_id: 'i1', element_id: 'G', name: '¿Se aprueba?', candidate_role: null, wait_kind: 'decision',
        process_name: 'Compras', variables: {}, created_at: '2026-11-04T10:00:00Z',
        options: [{ flow_id: 'si', name: 'Sí', default: false }, { flow_id: 'no', name: 'No', default: false }] },
    ]
    montar(<BpmInbox />)
    expect(await screen.findByText('[bpm.rol_cualquiera]')).toBeTruthy()
    fireEvent.click(await screen.findByText('bpm.decidir'))
    const botones = await screen.findAllByText('bpm.decidir')
    const confirmar = botones.at(-1)!.closest('button')!
    expect(confirmar.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('bpm.elige_salida'), { target: { value: 'no' } })
    expect(confirmar.disabled).toBe(false)
    fireEvent.click(confirmar)
    await waitFor(() => expect(complete).toHaveBeenCalledWith('i1', 's2', { variables: {}, flow_id: 'no' }))
  })

  it('traduce el motivo del fallo, el tipo y el rol desde sus códigos', async () => {
    montar(<BpmRunPanel />)
    fireEvent.click(await screen.findByText('bpm.ver'))
    expect(await screen.findByText('[bpm.error_no_route:Importe]')).toBeTruthy()
    expect(screen.queryByText('texto del backend')).toBeNull()
    expect(screen.getByText('[bpm.tipo_userTask] · [bpm.rol_hr]')).toBeTruthy()
  })
})
