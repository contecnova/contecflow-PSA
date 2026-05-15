import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TimerWidget from '../components/TimerWidget'

const { authState, apiMock } = vi.hoisted(() => ({
  authState: { user: { id: 'u1', hourly_rate: 50 } },
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => authState,
}))

vi.mock('../services/api', () => ({
  default: apiMock,
}))

function renderWithQueryClient(ui) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  })
  return render(
    <QueryClientProvider client={client}>
      {ui}
    </QueryClientProvider>
  )
}

describe('TimerWidget', () => {
  beforeEach(() => {
    authState.user = { id: 'u1', hourly_rate: 50 }
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.patch.mockReset()
    apiMock.delete.mockReset()
  })

  it('renderiza el componente TimerWidget con el formato HH:MM:SS', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url === '/imputations/timer/current') {
        return Promise.resolve({
          data: {
            id: 'timer-1',
            project_id: 'proj-1',
            started_at: new Date().toISOString(),
            paused_at: null,
            paused_duration_secs: 0,
            total_elapsed_seconds: null,
          },
        })
      }
      if (url === '/projects?page_size=100') {
        return Promise.resolve({ data: [] })
      }
      return Promise.resolve({ data: [] })
    })

    renderWithQueryClient(<TimerWidget />)
    await waitFor(() =>
      expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
    )
  })

  it('no bloquea iniciar por falta de hourly_rate en el contexto auth', async () => {
    authState.user = { id: 'u1' }
    apiMock.get.mockImplementation((url) => {
      if (url === '/imputations/timer/current') {
        return Promise.resolve({ data: null })
      }
      if (url === '/projects?page_size=100') {
        return Promise.resolve({ data: [{ id: 'proj-1', name: 'Proyecto demo' }] })
      }
      return Promise.resolve({ data: [] })
    })
    apiMock.post.mockResolvedValue({
      data: {
        id: 'timer-1',
        project_id: 'proj-1',
        started_at: new Date().toISOString(),
        paused_at: null,
        paused_duration_secs: 0,
        total_elapsed_seconds: null,
      },
    })

    renderWithQueryClient(<TimerWidget />)

    const projectSelect = await screen.findByDisplayValue('— Proyecto —')
    expect(screen.queryByText(/Sin tarifa horaria asignada/i)).not.toBeInTheDocument()

    fireEvent.change(projectSelect, { target: { value: 'proj-1' } })
    fireEvent.click(screen.getByRole('button', { name: /Iniciar/i }))

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith('/imputations/timer/start', { project_id: 'proj-1' })
    })
  })

  it('no fuerza duplicado automáticamente en stop', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url === '/imputations/timer/current') {
        return Promise.resolve({
          data: {
            id: 'timer-1',
            project_id: 'proj-1',
            started_at: new Date().toISOString(),
            paused_at: null,
            paused_duration_secs: 0,
            total_elapsed_seconds: null,
          },
        })
      }
      if (url === '/projects?page_size=100') {
        return Promise.resolve({ data: [] })
      }
      return Promise.resolve({ data: [] })
    })

    apiMock.post
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Ya existe una imputación para esta tarea en esa fecha.' } } })

    renderWithQueryClient(<TimerWidget />)

    await screen.findByText(/\d{2}:\d{2}:\d{2}/)
    fireEvent.click(screen.getByRole('button', { name: '⏹' }))

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledTimes(1)
      expect(apiMock.post).toHaveBeenCalledWith('/imputations/timer/stop', {
        description: 'Sesión',
        is_billable: true,
      })
    })

    expect(await screen.findByText(/Ya existe una imputación/i)).toBeInTheDocument()
  })
})
