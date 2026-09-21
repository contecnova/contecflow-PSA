import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TimerWidget from '../components/TimerWidget'
import { AppLangProvider } from '../i18n/AppLangContext';

// TimerWidget usa los helpers `imputationsApi` / `projectsApi` (no el axios crudo),
// y `useAuth` del contexto. Mockeamos exactamente esos exports.
const { authState, imputationsApi, projectsApi } = vi.hoisted(() => ({
  authState: { user: { id: 'u1', hourly_rate: 50 } },
  imputationsApi: {
    timerCurrent: vi.fn(),
    timerStart: vi.fn(),
    timerStop: vi.fn(),
    timerPause: vi.fn(),
    timerResume: vi.fn(),
  },
  projectsApi: {
    list: vi.fn(),
  },
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => authState,
  AuthContext: {},
}))

vi.mock('../services/api', () => ({
  imputationsApi,
  projectsApi,
}))

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  })
  // `TimerWidget` pasa ahora su texto por `t()`, y `useAppLang` lanza a
  // proposito si no encuentra el proveedor: es la guarda que impide usar la
  // traduccion fuera del arbol donde existe. Lo correcto es que el test monte
  // el contexto, no debilitar la guarda para que el test pase. El proveedor ya
  // contempla Vitest —`loading` arranca en `false`—, asi que pinta de
  // inmediato.
  return render(
    <AppLangProvider>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </AppLangProvider>,
  )
}

const runningTimer = {
  id: 'timer-1',
  project_id: 'proj-1',
  started_at: new Date().toISOString(),
  paused_at: null,
  paused_duration_secs: 0,
  total_elapsed_seconds: null,
}

describe('TimerWidget', () => {
  beforeEach(() => {
    authState.user = { id: 'u1', hourly_rate: 50 }
    imputationsApi.timerCurrent.mockReset()
    imputationsApi.timerStart.mockReset()
    imputationsApi.timerStop.mockReset()
    imputationsApi.timerPause.mockReset()
    imputationsApi.timerResume.mockReset()
    projectsApi.list.mockReset()
    projectsApi.list.mockResolvedValue({ data: [] })
  })

  it('renderiza el componente TimerWidget con el formato HH:MM:SS', async () => {
    imputationsApi.timerCurrent.mockResolvedValue({ data: runningTimer })

    renderWithQueryClient(<TimerWidget />)
    await waitFor(() =>
      expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
    )
  })

  it('no bloquea iniciar por falta de hourly_rate en el contexto auth', async () => {
    // Sin `hourly_rate` a proposito: es exactamente el caso que prueba.
    authState.user = { id: 'u1' } as typeof authState.user
    imputationsApi.timerCurrent.mockResolvedValue({ data: null })
    projectsApi.list.mockResolvedValue({ data: [{ id: 'proj-1', name: 'Proyecto demo' }] })
    imputationsApi.timerStart.mockResolvedValue({ data: runningTimer })

    renderWithQueryClient(<TimerWidget />)

    const projectSelect = await screen.findByDisplayValue('— Proyecto —')
    expect(screen.queryByText(/Sin tarifa horaria asignada/i)).not.toBeInTheDocument()

    fireEvent.change(projectSelect, { target: { value: 'proj-1' } })
    fireEvent.click(screen.getByRole('button', { name: /Iniciar/i }))

    await waitFor(() => {
      // project_id debe viajar como el string del proyecto (no Number()), que es lo
      // que exige el backend (TimerStartPayload.project_id: str).
      expect(imputationsApi.timerStart).toHaveBeenCalledWith({ project_id: 'proj-1' })
    })
  })

  it('no fuerza duplicado automáticamente en stop', async () => {
    imputationsApi.timerCurrent.mockResolvedValue({ data: runningTimer })
    imputationsApi.timerStop.mockRejectedValueOnce({
      response: { status: 409, data: { detail: 'Ya existe una imputación para esta tarea en esa fecha.' } },
    })

    renderWithQueryClient(<TimerWidget />)

    await screen.findByText(/\d{2}:\d{2}:\d{2}/)
    fireEvent.click(screen.getByRole('button', { name: '⏹' }))

    await waitFor(() => {
      expect(imputationsApi.timerStop).toHaveBeenCalledTimes(1)
      expect(imputationsApi.timerStop).toHaveBeenCalledWith({
        description: 'Sesión',
        is_billable: true,
      })
    })

    expect(await screen.findByText(/Ya existe una imputación/i)).toBeInTheDocument()
  })
})
