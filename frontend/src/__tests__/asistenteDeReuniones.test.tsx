// Asistente de reuniones (19-11-2026): pantalla, grabador, configuración y permisos.
// Ver docs/ASISTENTE_DE_REUNIONES.md.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

const { api, estado, toast } = vi.hoisted(() => {
  const nombres = ['listar', 'crear', 'detalle', 'editar', 'borrar', 'subirTrozo', 'terminar', 'reprocesar', 'audio', 'trozo',
    'borrarAudio', 'transcripcion', 'editarSegmento', 'anadirParticipante', 'quitarParticipante', 'consentir', 'editarAccion',
    'crearTarea', 'crearTicket', 'crearTareas', 'generarActa', 'preguntar', 'buscar', 'invitarBot', 'sacarBot', 'importar',
    'preferencias', 'guardarPreferencias', 'config', 'guardarConfig', 'probar', 'suscripcionTeams', 'copiaRgpd', 'suprimirRgpd']
  return {
    api: Object.fromEntries(nombres.map(n => [n, vi.fn()])) as Record<string, ReturnType<typeof vi.fn>>,
    estado: { capacidades: ['reuniones.usar', 'reuniones.config'] as string[] },
    toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  }
})

vi.mock('../services/api/reuniones', () => ({
  reunionesApi: api,
  ESTADOS_REUNION: ['programada', 'bot_unido', 'grabando', 'procesando', 'esperando_consentimiento', 'lista', 'error'],
  ORIGENES_REUNION: ['transcript', 'upload', 'recording', 'bot', 'teams', 'zoom', 'meet'],
  ESTADOS_EN_CURSO: ['programada', 'bot_unido', 'grabando', 'procesando'],
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => toast }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', role: 'admin' }, puede: (c: string) => estado.capacidades.includes(c) }),
}))
vi.mock('../i18n/AppLangContext', () => {
  const t = (k: string) => k
  return { useAppLang: () => ({ t, lang: 'es' }), useAppT: () => t }
})
vi.mock('../components/layout/PageHeader', () => ({
  default: ({ title, actions }: { title?: ReactNode; actions?: ReactNode }) => <header><h1>{title}</h1>{actions}</header>,
}))
vi.mock('../components/layout/PageShell', () => ({ default: ({ children }: { children?: ReactNode }) => <main>{children}</main> }))
vi.mock('../hooks/useMediaQuery', () => ({ default: () => false }))

import MeetingsAIPage from '../pages/MeetingsAIPage'
import GrabadorDeReunion from '../components/reuniones/GrabadorDeReunion'
import ConfigReuniones from '../components/reuniones/ConfigReuniones'
import { CAPACIDADES } from '../permisos/capacidades'
import { RUTAS } from '../permisos/navegacion'
import { SECCIONES_DE_AJUSTES } from '../pages/settings/catalogoDeAjustes'

const pintar = (ui: ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>,
)

const REUNIONES = [
  {
    id: 'm1', title: 'Revisión semanal', status: 'lista', origin: 'teams', platform: 'teams', project_id: 'p1', project_name: 'Alfa',
    client_id: null, client_name: null, meeting_date: '2026-11-18T10:00:00Z', duration_min: 30, actions_count: 3, created_actions: 1,
    has_audio: false, consent_pending: false, bot_status: null, error_code: null, created_at: '2026-11-18T10:00:00Z', can_manage: true,
  },
  {
    id: 'm2', title: 'Taller con el cliente', status: 'grabando', origin: 'recording', platform: null, project_id: null, project_name: null,
    client_id: null, client_name: null, meeting_date: null, duration_min: null, actions_count: 0, created_actions: 0,
    has_audio: true, consent_pending: true, bot_status: null, error_code: null, created_at: '2026-11-19T09:00:00Z', can_manage: true,
  },
]

const CONFIG = {
  consent: { notice_required: true, require_consent: false, notice_text: 'Esta reunión se graba', bot_message: 'Hola, grabo' },
  retention: { audio_days: 7, transcript_days: 365 },
  translation: { per_person: true },
  linking: { auto: true },
  transcription: { allow_external_stt: false, external_stt_contract: '', stt_providers: ['whisper_local'], stt_effective: 'whisper_local' },
  teams: {
    enabled: true, tenant_id: 'tenant-1', client_id: 'cli-1', secret_set: true, mode: 'polling', client_state_set: true,
    subscription_id: null, subscription_expires_at: null, webhook_url: 'https://x/api/v1/webhooks/meetings/teams/o1',
  },
  zoom: { enabled: false, account_id: '', client_id: '', secret_set: true, webhook_secret_set: true, webhook_url: 'https://x/zoom' },
  meet: { enabled: false, service_account_email: '', key_set: true },
  bots: {
    enabled: false, provider: 'recall', providers: ['recall'], region: 'eu-central-1', api_key_set: true, webhook_secret_set: false,
    bot_name: 'Asistente', contract_reference: '', contract_accepted_by: null, contract_accepted_at: null, webhook_url: 'https://x/recall',
  },
}

beforeEach(() => {
  estado.capacidades = ['reuniones.usar', 'reuniones.config']
  Object.values(api).forEach(f => f.mockReset())
  Object.values(toast).forEach(f => f.mockReset())
  api.listar.mockResolvedValue(REUNIONES)
  api.preferencias.mockResolvedValue({ collect_teams: false, collect_meet: false, bot_for_my_calendar: false, language: null, available: { teams: true, meet: false, bots: true } })
  api.buscar.mockResolvedValue([])
  api.config.mockResolvedValue(structuredClone(CONFIG))
  api.guardarConfig.mockImplementation(async (c: unknown) => ({ ...structuredClone(CONFIG), ...(c as object) }))
})

describe('pantalla del asistente de reuniones', () => {
  it('pinta la lista con estado y origen y los KPIs, sin botón Configurar', async () => {
    pintar(<MeetingsAIPage />)
    expect(await screen.findByText('Revisión semanal')).toBeTruthy()
    expect(screen.getByText('Taller con el cliente')).toBeTruthy()
    expect(screen.getAllByText('reuniones.estado.lista').length).toBeGreaterThan(0)
    expect(screen.getAllByText('reuniones.estado.grabando').length).toBeGreaterThan(0)
    expect(screen.getByText('reuniones.origen.teams')).toBeTruthy()
    expect(screen.getByText('reuniones.origen.recording')).toBeTruthy()
    expect(screen.getByText('reuniones.kpi.en_curso')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /ajustes\.configurar/ })).toBeNull()
    expect(api.listar).toHaveBeenCalled()
  })

  it('sin reuniones.config no hay botón Configurar', async () => {
    estado.capacidades = ['reuniones.usar']
    pintar(<MeetingsAIPage />)
    await screen.findByText('Revisión semanal')
    expect(screen.queryByRole('button', { name: /ajustes\.configurar/ })).toBeNull()
  })
})

describe('grabador', () => {
  it('no deja empezar sin confirmar el aviso de grabación', async () => {
    pintar(<GrabadorDeReunion onClose={() => undefined} />)
    const empezar = screen.getByRole('button', { name: /reuniones\.grabador\.empezar/ }) as HTMLButtonElement
    expect(empezar.disabled).toBe(true)
    fireEvent.click(empezar)
    expect(api.crear).not.toHaveBeenCalled()

    fireEvent.click(screen.getByLabelText('reuniones.grabador.he_avisado'))
    expect(empezar.disabled).toBe(false)
  })

  it('con el aviso confirmado pero sin soporte de grabación avisa y no crea la reunión', async () => {
    const original = (globalThis as { MediaRecorder?: unknown }).MediaRecorder
    delete (globalThis as { MediaRecorder?: unknown }).MediaRecorder
    pintar(<GrabadorDeReunion onClose={() => undefined} />)
    fireEvent.click(screen.getByLabelText('reuniones.grabador.he_avisado'))
    fireEvent.click(screen.getByRole('button', { name: /reuniones\.grabador\.empezar/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('reuniones.grabador.no_soportado'))
    expect(api.crear).not.toHaveBeenCalled()
    if (original) (globalThis as { MediaRecorder?: unknown }).MediaRecorder = original
  })
})

describe('configuración del asistente de reuniones', () => {
  it('no muestra secretos: los campos de secreto llegan vacíos', async () => {
    pintar(<ConfigReuniones />)
    await screen.findByTestId('config-reuniones')
    const secretos = Array.from(document.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
    expect(secretos.length).toBeGreaterThan(0)
    for (const s of secretos) expect(s.value).toBe('')
    const clave = document.querySelector('textarea.reu-secreto') as HTMLTextAreaElement
    expect(clave.value).toBe('')
  })

  it('el bot no se activa sin contrato y guardar manda contract_reference sin secretos vacíos', async () => {
    pintar(<ConfigReuniones />)
    await screen.findByTestId('config-reuniones')
    const interruptores = screen.getAllByRole('switch', { name: /reuniones\.config\.activo/ }) as HTMLInputElement[]
    const delBot = interruptores[interruptores.length - 1]
    expect(delBot.disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('reuniones.config.contrato'), { target: { value: 'DPA-2026-01' } })
    expect(delBot.disabled).toBe(false)
    fireEvent.click(delBot)
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))

    await waitFor(() => expect(api.guardarConfig).toHaveBeenCalled())
    const cuerpo = api.guardarConfig.mock.calls[0][0] as { bots: Record<string, unknown>; teams: Record<string, unknown> }
    expect(cuerpo.bots.contract_reference).toBe('DPA-2026-01')
    expect(cuerpo.bots.enabled).toBe(true)
    expect(cuerpo.bots.api_key).toBeUndefined()
    expect(cuerpo.teams.client_secret).toBeUndefined()
  })
})

describe('permisos del asistente de reuniones', () => {
  it('existen las capacidades nuevas y la ruta y la sección las usan', () => {
    for (const c of ['reuniones.usar', 'reuniones.ver_todas', 'reuniones.config']) expect(CAPACIDADES).toContain(c)
    expect(RUTAS.find(r => r.patron === '/meetings-ai')?.capacidad).toBe('reuniones.usar')
    const seccion = SECCIONES_DE_AJUSTES.find(s => s.id === 'reuniones')
    expect(seccion?.grupo).toBe('ia')
    expect(seccion?.capacidad).toBe('reuniones.config')
  })
})
