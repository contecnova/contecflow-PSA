/**
 * MeetingsAIPage — Asistente de reuniones (rehecha el 19-11-2026).
 *
 * Pantalla operativa (la configuración vive en Configuración → IA e idiomas →
 * Asistente de reuniones, `/settings/reuniones`, con `reuniones.config`).
 * Sin botón «Configurar»: solo un aviso con enlace «Ir a Configuración» donde
 * una acción no funciona por falta de configuración (bot, conectores) y solo
 * con `reuniones.config`. Diseño: docs/ASISTENTE_DE_REUNIONES.md.
 *
 * - Cabecera: Grabar (micrófono o pestaña, aviso obligatorio), Invitar el bot,
 *   Traer de Teams/Zoom/Meet, Pegar transcripción y Mis preferencias.
 * - Buscador sobre lo visible (`/meeting-assistant/search`): título, resumen y
 *   lo dicho; abre la reunión y resalta el turno encontrado.
 * - KPIs, filtro por estado y lista con estado y origen; detalle a la derecha.
 * - Refresco cada 5 s mientras alguna reunión está en curso.
 * - `?meeting=<id>` abre esa reunión (enlace del acta que el asistente publica en el chat).
 *
 * Ruta `/meetings-ai` con la capacidad `reuniones.usar` (antes `proyectos.trabajo`).
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Bot, ClipboardPaste, Download, ListChecks, Loader2, Mic, MousePointerClick, Search, ShieldAlert, SlidersHorizontal,
} from 'lucide-react'
import { Button, Card, EmptyState, Input, KpiCard, Pulsable, Select, Spinner } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { fmtDate } from '../utils/helpers'
import { reunionesApi, ESTADOS_REUNION } from '../services/api/reuniones'
import { CLAVES, EstadoDeReunion, OrigenDeReunion, REFRESCO_EN_CURSO_MS, enCurso } from '../components/reuniones/comun'
import DetalleDeReunion from '../components/reuniones/DetalleDeReunion'
import GrabadorDeReunion from '../components/reuniones/GrabadorDeReunion'
import ModalInvitarBot from '../components/reuniones/ModalInvitarBot'
import ModalImportar from '../components/reuniones/ModalImportar'
import ModalPegarTranscripcion from '../components/reuniones/ModalPegarTranscripcion'
import ModalPreferencias from '../components/reuniones/ModalPreferencias'
import './MeetingsAIPage.css'

type ModalAbierto = 'grabar' | 'bot' | 'importar' | 'pegar' | 'preferencias' | null

/** Espera a que se deje de escribir antes de buscar. */
function useRetrasado<T>(valor: T, ms = 350): T {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const h = setTimeout(() => setV(valor), ms)
    return () => clearTimeout(h)
  }, [valor, ms])
  return v
}

export default function MeetingsAIPage() {
  const t = useAppT()
  const configura = useAuth().puede('reuniones.config')
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const [modal, setModal] = useState<ModalAbierto>(null)
  const [params] = useSearchParams()
  const deLaUrl = params.get('meeting')
  const [seleccionada, setSeleccionada] = useState<string | null>(deLaUrl)
  useEffect(() => { if (deLaUrl) setSeleccionada(deLaUrl) }, [deLaUrl])
  const [resaltado, setResaltado] = useState<string | null>(null)
  const [estado, setEstado] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const q = useRetrasado(busqueda.trim())

  const { data: reuniones = [], isLoading } = useQuery({
    queryKey: [...CLAVES.lista, estado],
    queryFn: () => reunionesApi.listar({ status: estado || undefined }),
    refetchInterval: query => ((query.state.data ?? []).some(r => enCurso(r.status)) ? REFRESCO_EN_CURSO_MS : false),
  })
  const { data: resultados = [], isFetching: buscando } = useQuery({
    queryKey: ['reuniones-busqueda', q],
    queryFn: () => reunionesApi.buscar(q),
    enabled: q.length >= 2,
  })
  const { data: prefs } = useQuery({ queryKey: CLAVES.preferencias, queryFn: reunionesApi.preferencias, staleTime: 60_000 })

  const kpis = useMemo(() => ({
    total: reuniones.length,
    enCurso: reuniones.filter(r => enCurso(r.status)).length,
    consentimiento: reuniones.filter(r => r.status === 'esperando_consentimiento' || r.consent_pending).length,
    acciones: reuniones.reduce((a, r) => a + (r.actions_count || 0), 0),
    creadas: reuniones.reduce((a, r) => a + (r.created_actions || 0), 0),
  }), [reuniones])

  const abrir = (id: string, segmento: string | null = null) => {
    setSeleccionada(id)
    setResaltado(segmento)
  }
  const cerrarModal = () => setModal(null)
  const botDesactivado = prefs?.available ? !prefs.available.bots : false

  return (
    <PageShell>
      <PageHeader
        icon={<Mic size={18} />}
        title={t('nav.meetings')}
        subtitle={t('reuniones.subtitulo')}
        showListExport={false}
        actions={(
          <div className="meet-cabecera">
            <Button icon={<Mic size={14} />} onClick={() => setModal('grabar')}>{t('reuniones.grabar')}</Button>
            <Button variant="secondary" icon={<Bot size={14} />} onClick={() => setModal('bot')} disabled={botDesactivado}
              title={botDesactivado ? t('err_srv.reuniones_bots_desactivados') : undefined}>
              {t('reuniones.invitar_bot')}
            </Button>
            <Button variant="secondary" icon={<Download size={14} />} onClick={() => setModal('importar')}>{t('reuniones.traer')}</Button>
            <Button variant="secondary" icon={<ClipboardPaste size={14} />} onClick={() => setModal('pegar')}>{t('reuniones.pegar_transcripcion')}</Button>
            <Button variant="ghost" icon={<SlidersHorizontal size={14} />} onClick={() => setModal('preferencias')}>{t('reuniones.mis_preferencias')}</Button>
          </div>
        )}
      />

      <div className="u-stack-16">
        {botDesactivado && (
          <p className="u-text3-xs" role="status">
            {t('reuniones.bot_sin_activar')}{' '}
            {configura && <Link to="/settings/reuniones">{t('reuniones.ir_a_configuracion')}</Link>}
          </p>
        )}
        <div className="meet-filtros">
          <Input className="meet-filtros__buscar" aria-label={t('reuniones.buscar')} placeholder={t('reuniones.buscar_placeholder')}
            value={busqueda} onChange={e => setBusqueda(e.target.value)} />
          <Select suelto aria-label={t('reuniones.filtro_estado')} value={estado} onChange={e => setEstado(e.target.value)}
            placeholder={t('reuniones.todos_los_estados')}
            options={ESTADOS_REUNION.map(s => ({ value: s, label: t(`reuniones.estado.${s}`) }))} />
        </div>

        {q.length >= 2 && (
          <Card>
            <div className="meet-busqueda">
              <div className="meet-busqueda__cab">
                <Search size={14} aria-hidden />
                <span>{t('reuniones.resultados', { n: resultados.length })}</span>
                {buscando && <Loader2 size={14} className="meet-girando" aria-hidden />}
              </div>
              {resultados.length === 0 && !buscando ? <p className="u-text3-xs">{t('reuniones.sin_resultados')}</p> : (
                <ul className="meet-busqueda__lista">
                  {resultados.map((res, i) => (
                    <li key={`${res.meeting_id}-${res.segment_id ?? i}`}>
                      <Pulsable className="meet-resultado" onClick={() => abrir(res.meeting_id, res.segment_id)}>
                        <span className="meet-resultado__titulo">{res.title}</span>
                        <span className="meet-resultado__fecha">{fmtDate(res.meeting_date)}</span>
                        <span className="meet-resultado__texto">{res.snippet}</span>
                      </Pulsable>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        )}

        {reuniones.length > 0 && (
          <div className="ds-grid-stats">
            <KpiCard icon={<Mic size={16} />} label={t('reuniones.kpi.reuniones')} value={kpis.total} />
            <KpiCard icon={<Loader2 size={16} />} label={t('reuniones.kpi.en_curso')} value={kpis.enCurso} accent={kpis.enCurso > 0} />
            <KpiCard icon={<ShieldAlert size={16} />} label={t('reuniones.kpi.consentimiento')} value={kpis.consentimiento} warning={kpis.consentimiento > 0} />
            <KpiCard icon={<ListChecks size={16} />} label={t('reuniones.kpi.acciones')} value={kpis.acciones}
              sub={t('reuniones.kpi.tareas_creadas', { n: kpis.creadas })} />
          </div>
        )}

        {isLoading ? <Spinner /> : reuniones.length === 0 ? (
          <Card>
            <EmptyState icon={<Mic size={28} />} title={t('reuniones.vacio_titulo')} description={t('reuniones.vacio_desc')}
              action={<Button icon={<Mic size={14} />} onClick={() => setModal('grabar')}>{t('reuniones.grabar')}</Button>} />
          </Card>
        ) : (
          <div className={`meet-layout${isNarrow ? ' meet-layout--estrecho' : ''}`}>
            <ul className="meet-lista" aria-label={t('reuniones.lista')}>
              {reuniones.map(m => {
                const activa = seleccionada === m.id
                return (
                  <li key={m.id}>
                    <Pulsable onClick={() => abrir(m.id)} aria-pressed={activa} className={`meet-item${activa ? ' meet-item--activa' : ''}`}>
                      <div className="meet-item__titulo">{m.title}</div>
                      <div className="meet-item__fecha">
                        {fmtDate(m.meeting_date || m.created_at)}
                        {m.project_name ? ` · ${m.project_name}` : ''}
                      </div>
                      <div className="meet-item__pie">
                        <EstadoDeReunion estado={m.status} />
                        <OrigenDeReunion origen={m.origin} />
                        {m.actions_count > 0 && (
                          <span className="meet-item__dato">{t('reuniones.n_acciones', { n: m.actions_count, creadas: m.created_actions })}</span>
                        )}
                        {m.consent_pending && <span className="meet-item__dato meet-item__dato--aviso">{t('reuniones.consentimiento.pendiente')}</span>}
                      </div>
                    </Pulsable>
                  </li>
                )
              })}
            </ul>

            <div className="u-min0">
              {!seleccionada ? (
                <Card>
                  <EmptyState icon={<MousePointerClick size={28} />} title={t('reuniones.elige_titulo')} description={t('reuniones.elige_desc')} />
                </Card>
              ) : (
                <DetalleDeReunion key={seleccionada} id={seleccionada} segmentoResaltado={resaltado} onBorrada={() => setSeleccionada(null)} />
              )}
            </div>
          </div>
        )}
      </div>

      {modal === 'grabar' && <GrabadorDeReunion onClose={cerrarModal} onCreada={id => abrir(id)} />}
      {modal === 'bot' && <ModalInvitarBot onClose={cerrarModal} onCreada={id => abrir(id)} />}
      {modal === 'importar' && <ModalImportar onClose={cerrarModal} onCreada={id => abrir(id)} disponibles={prefs?.available ? { teams: prefs.available.teams, meet: prefs.available.meet } : undefined} />}
      {modal === 'pegar' && <ModalPegarTranscripcion onClose={cerrarModal} onCreada={id => abrir(id)} />}
      {modal === 'preferencias' && <ModalPreferencias onClose={cerrarModal} />}
    </PageShell>
  )
}
