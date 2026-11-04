// Auditoría 2026-11: /bpm no ejecutaba nada. La bandeja enseña los pasos
// humanos pendientes y completarlos manda las variables al motor.
import { vi, describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const complete = vi.fn(() => Promise.resolve({ data: {} }))
vi.mock('../services/api', () => ({
  apiErrorMsg: () => 'error',
  bpmnInstancesApi: {
    inbox: () => Promise.resolve({ data: [
      { id: 's1', instance_id: 'i1', element_id: 'Revisar', name: 'Revisar solicitud', candidate_role: 'pm',
        process_name: 'Compras', variables: { importe: 500 } },
    ] }),
    list: () => Promise.resolve({ data: [
      { id: 'i1', process_name: 'Compras', status: 'running', active_steps: ['Revisar solicitud'], started_at: '2026-11-04T10:00:00' },
    ] }),
    get: vi.fn(), cancel: vi.fn(),
    complete: (...a: unknown[]) => complete(...a),
  },
}))
vi.mock('../i18n/AppLangContext', () => ({ useAppLang: () => ({ t: (k: string) => k }) }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }))

import BpmRunPanel from '../pages/bpm/BpmRunPanel'

describe('BpmRunPanel', () => {
  it('completa un paso de la bandeja con las variables escritas', async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BpmRunPanel />
      </QueryClientProvider>,
    )
    expect(await screen.findAllByText('Revisar solicitud')).toHaveLength(2)
    fireEvent.click(screen.getAllByText('bpm.completar')[0])
    fireEvent.change(await screen.findByLabelText('bpm.variables_ayuda'), { target: { value: 'aprobada=true\nimporte=900' } })
    fireEvent.click(screen.getAllByText('bpm.completar').at(-1)!)
    await waitFor(() => expect(complete).toHaveBeenCalledWith('i1', 's1', { aprobada: true, importe: 900 }))
  })
})
