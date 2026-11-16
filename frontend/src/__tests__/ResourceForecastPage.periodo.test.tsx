// Periodo libre (16-11-2026): el horizonte de la previsión de recursos es el
// selector de periodo común hacia delante, no un desplegable de semanas.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
  useAppT: () => (k: string) => k,
}))
// jsdom no trae matchMedia; el mapa de calor ajusta el ancho de nombres con
// useMediaQuery (como en BIPage.test, se fija a escritorio).
vi.mock('../hooks/useMediaQuery', () => ({ default: () => false }))
// PageShell pinta el botón de exportar la lista, que avisa con useToast.
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('../services/api/periodo', () => ({
  periodoApi: { limites: () => Promise.resolve({ max_dias: 1830, max_puntos: { hour: 744, day: 1100, week: 530, month: 240 }, auto_max_puntos: 120, granularidades: [] }) },
}))
const heatmap = vi.fn().mockResolvedValue({ data: { from_date: '2026-11-16', weeks: 13, week_labels: [], users: [] } })
const summary = vi.fn().mockResolvedValue({ data: { total_users: 0, weeks: 13, week_trend: [], risk_weeks: [] } })
vi.mock('../services/api', () => ({
  forecastApi: {
    heatmap: (p: unknown) => heatmap(p),
    summary: (p: unknown) => summary(p),
    userDetail: vi.fn().mockResolvedValue({ data: null }),
  },
}))

import ResourceForecastPage from '../pages/ResourceForecastPage'

function montar(ruta = '/resource-forecast') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <QueryClientProvider client={qc}>
        <ResourceForecastPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('ResourceForecastPage — horizonte con periodo libre', () => {
  beforeEach(() => { heatmap.mockClear(); summary.mockClear() })

  it('por defecto pide los próximos 90 días (≈ 13 semanas) al mapa y al resumen', async () => {
    montar()
    await waitFor(() => expect(heatmap).toHaveBeenCalled())
    expect(heatmap.mock.calls[0][0]).toMatchObject({ days: 90 })
    expect(heatmap.mock.calls[0][0]).not.toHaveProperty('weeks')
    await waitFor(() => expect(summary).toHaveBeenCalled())
    expect(summary.mock.calls[0][0]).toMatchObject({ days: 90 })
  })

  it('un rango personalizado de la URL va como desde/hasta', async () => {
    montar('/resource-forecast?periodo=custom&desde=2027-01-04T00:00:00%2B01:00&hasta=2027-03-01T00:00:00%2B01:00')
    await waitFor(() => expect(heatmap).toHaveBeenCalled())
    expect(heatmap.mock.calls[0][0]).toMatchObject({ desde: '2027-01-04T00:00:00+01:00', hasta: '2027-03-01T00:00:00+01:00' })
  })

  it('ya no hay desplegable de N semanas ni «próximos 365 días»', () => {
    const { queryByText } = montar()
    expect(queryByText('prevision_recursos_ui.n_semanas')).toBeNull()
    expect(queryByText('periodo.prox365d')).toBeNull()
  })
})
