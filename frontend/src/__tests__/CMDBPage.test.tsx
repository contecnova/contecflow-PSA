// Auditoría 2026-11: la pantalla CMDB editaba `cmdb_items`, una CMDB que los
// tickets no veían. Ahora lee y escribe en `/sd/cmdb`.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const sdList = vi.fn()
const sdCreate = vi.fn()

vi.mock('../services/api', () => ({
  cmdbApi: {
    sdList: (...a: unknown[]) => sdList(...a),
    sdCreate: (...a: unknown[]) => sdCreate(...a),
    sdUpdate: vi.fn(), sdDelete: vi.fn(), sdChangelog: vi.fn(), sdRelations: vi.fn(),
    sdCreateRelation: vi.fn(), sdDeleteRelation: vi.fn(), topology: vi.fn(),
    agents: vi.fn().mockResolvedValue({ data: [] }), registerAgent: vi.fn(), deleteAgent: vi.fn(),
    assetsByCI: vi.fn().mockResolvedValue({ data: [] }),
    classFields: vi.fn().mockResolvedValue({ data: { por_defecto: true, clases: {
      server: [{ key: 'os', label: null, field_type: 'text' }],
      database: [{ key: 'db_engine', label: null, field_type: 'text' }, { key: 'puerto', label: 'Puerto propio', field_type: 'number' }],
    } } }),
    saveClassFields: vi.fn(),
  },
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/ConfirmContext', () => ({ openConfirmGlobal: vi.fn() }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'admin' } }) }))
vi.mock('../components/layout/PageHeader', () => ({ default: ({ actions }: { actions: JSX.Element }) => <div>{actions}</div> }))
vi.mock('../components/layout/PageShell', () => ({ default: ({ children }: { children: JSX.Element }) => <div>{children}</div> }))

import CMDBPage from '../pages/CMDBPage'

const pintar = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <CMDBPage />
  </QueryClientProvider>,
)

describe('CMDBPage', () => {
  beforeEach(() => {
    sdList.mockReset().mockResolvedValue({ data: [
      { id: 'c1', code: 'CI-0001', name: 'web-prod-01', ci_type: 'server', status: 'operational',
        environment: 'production', hostname: 'web01', ip_address: '10.0.0.1', attributes: { os: 'Ubuntu' },
        is_discovered: true, discovery_provider: 'aws' },
    ] })
    sdCreate.mockReset().mockResolvedValue({ data: { id: 'c2' } })
  })

  it('enseña los CIs de la CMDB del service desk', async () => {
    pintar()
    expect(await screen.findByText('web-prod-01')).toBeTruthy()
    expect(screen.getByText('10.0.0.1')).toBeTruthy()
    expect(sdList).toHaveBeenCalledWith(expect.objectContaining({ page_size: 500 }))
  })

  it('al crear envía sólo los atributos de la clase elegida, según los campos del servidor', async () => {
    pintar()
    fireEvent.click(await screen.findByText('cmdb.new_ci'))
    fireEvent.change(screen.getByLabelText('cmdb.ci_name'), { target: { value: 'db-1' } })
    // Sin traducción (la prueba no carga idiomas) la etiqueta de fábrica es la clave.
    fireEvent.change(await screen.findByLabelText('os'), { target: { value: 'Linux' } })
    fireEvent.change(document.getElementById('ci-form-type')!, { target: { value: 'database' } })
    fireEvent.change(screen.getByLabelText('db_engine'), { target: { value: 'PostgreSQL' } })
    fireEvent.change(screen.getByLabelText('Puerto propio'), { target: { value: '5432' } })
    fireEvent.click(screen.getByText('cmdb.create'))
    await waitFor(() => expect(sdCreate).toHaveBeenCalled())
    const enviado = sdCreate.mock.calls[0][0]
    expect(enviado).toMatchObject({ name: 'db-1', ci_type: 'database', status: 'operational', hostname: null })
    expect(enviado.attributes).toEqual({ db_engine: 'PostgreSQL', puerto: '5432' })
  })
})
