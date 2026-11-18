/**
 * Ausencias gobernadas por reglas (tarea #25, revisión 167).
 *
 * - Mis ausencias: saldos, lista con su estado (también «en lista de espera» y
 *   su puesto), detalle con línea de tiempo y documentos.
 * - Pedir: formulario con vista previa en vivo (plazas por día y turno, lista
 *   de espera, aprobaciones, documentos, saldo, avisos y bloqueos).
 * - Calendario de equipo y mapa de cobertura por turno.
 * - Por aprobar: la bandeja de quien decide, con explicación e impacto.
 * - Cuadrante y Cobertura (admin y RRHH): la planificación del día a día de
 *   los turnos (antes dentro de la configuración).
 *
 * 18-11-2026: la configuración (tipos, documentos, turnos, jornadas,
 * festivos, personas, horario, acceso especial y ejemplos) sale del módulo y
 * vive en Configuración (`/settings/ausencias`, AdminDeAusencias). Aquí queda
 * el botón «Configurar» para admin y RRHH, y `?tab=config` redirige allí.
 * `?tab=mias|equipo|aprobar|cuadrante|cobertura` abre esa pestaña si el rol
 * la ve.
 */
import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Grid3x3, Inbox, ListOrdered, Pencil, Plus, Settings2, Umbrella, X } from 'lucide-react'
import { ausenciasApi } from '../services/api/ausencias'
import type { AusenciaServida } from '../services/api/tipos-ausencias'
import { Button, EmptyState, Page, Spinner, Tabs, Pulsable, TablaSimple } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { confirmar } from '../context/ConfirmContext'
import FormularioDeAusencia from '../components/ausencias/FormularioDeAusencia'
import DetalleDeAusencia from '../components/ausencias/DetalleDeAusencia'
import BandejaDeAusencias from '../components/ausencias/BandejaDeAusencias'
import CalendarioDeEquipo from '../components/ausencias/CalendarioDeEquipo'
import CuadranteDeTurnos from '../components/ausencias/admin/CuadranteDeTurnos'
import { PanelDeCobertura } from '../components/ausencias/admin/MapaDeCobertura'
import { AvisoDeError } from '../components/ausencias/admin/comun'
import { EstadoDeAusenciaChip, TipoChip, cantidad, fecha, useTa } from '../components/ausencias/comun'
import TarjetasDeSaldo from '../components/ausencias/Saldos'

export default function AbsencesPage(): JSX.Element {
  const { t, ta } = useTa()
  const { hasRole } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const pedida = searchParams.get('tab')
  const gestiona = hasRole('admin', 'hr', 'pm', 'team_lead')
  const planifica = hasRole('admin', 'hr')
  const validas = ['mias', 'equipo', 'aprobar', ...(planifica ? ['cuadrante', 'cobertura'] : [])]
  const [tab, setTab] = useState(pedida && validas.includes(pedida) ? pedida : 'mias')
  const [pidiendo, setPidiendo] = useState(false)
  const [editando, setEditando] = useState<AusenciaServida | null>(null)
  const [abierta, setAbierta] = useState<string | null>(null)
  const items = [
    { id: 'mias', label: ta('tab_mias'), icon: <Umbrella size={14} /> },
    { id: 'equipo', label: ta('tab_equipo'), icon: <CalendarDays size={14} /> },
    { id: 'aprobar', label: ta('tab_aprobar'), icon: <Inbox size={14} /> },
    ...(planifica ? [
      { id: 'cuadrante', label: t('ausadm.tab_cuadrante'), icon: <CalendarDays size={14} /> },
      { id: 'cobertura', label: t('ausadm.tab_cobertura'), icon: <Grid3x3 size={14} /> },
    ] : []),
  ]
  // La configuración vive en Configuración (18-11-2026): los enlaces antiguos redirigen.
  if (pedida === 'config') return <Navigate to="/settings/ausencias" replace />
  return (
    <Page title={ta('titulo')} subtitle={ta('subtitulo')} icon={<Umbrella size={18} />}
      actions={<>
        {planifica && (
          <Button variant="secondary" icon={<Settings2 size={14} />} onClick={() => navigate('/settings/ausencias')}>{t('ajustes.configurar')}</Button>
        )}
        <Button icon={<Plus size={14} />} onClick={() => setPidiendo(true)}>{ta('pedir_ausencia')}</Button>
      </>}>
      <Tabs items={items} active={tab} onChange={setTab} ariaLabel={ta('secciones')} />
      <div className="aus-panel" role="tabpanel">
        {tab === 'mias' && <MisAusencias onAbrir={setAbierta} onEditar={setEditando} onPedir={() => setPidiendo(true)} />}
        {tab === 'equipo' && (gestiona ? <CalendarioDeEquipo onAbrir={setAbierta} />
          : <EmptyState svgIcon={<CalendarDays size={26} />} title={ta('solo_responsables')} description={ta('solo_responsables_texto')} />)}
        {tab === 'aprobar' && <BandejaDeAusencias onAbrir={setAbierta} />}
        {tab === 'cuadrante' && planifica && <CuadranteDeTurnos />}
        {tab === 'cobertura' && planifica && <PanelDeCobertura />}
      </div>
      {(pidiendo || editando) && (
        <FormularioDeAusencia abierto editar={editando} onCerrar={() => { setPidiendo(false); setEditando(null) }} />
      )}
      <DetalleDeAusencia id={abierta} onCerrar={() => setAbierta(null)} />
    </Page>
  )
}

function MisAusencias({ onAbrir, onEditar, onPedir }: {
  onAbrir: (id: string) => void; onEditar: (a: AusenciaServida) => void; onPedir: () => void
}) {
  const { ta } = useTa()
  const qc = useQueryClient()
  const saldos = useQuery({ queryKey: ['ausencias', 'saldos'], queryFn: () => ausenciasApi.saldos() })
  const mias = useQuery({ queryKey: ['ausencias', 'mias'], queryFn: ausenciasApi.mias })
  const cancelar = useMutation({
    mutationFn: (id: string) => ausenciasApi.cancelar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ausencias'] }),
  })
  const pedirCancelar = async (a: AusenciaServida) => {
    if (await confirmar({ title: ta('cancelar_ausencia'), message: ta('cancelar_ausencia_texto'), danger: true })) cancelar.mutate(a.id)
  }
  return (
    <div className="aus-mias">
      {saldos.isError && <AvisoDeError error={saldos.error} defecto={ta('error_cargar')} />}
      <TarjetasDeSaldo saldos={saldos.data ?? []} />
      {mias.isLoading && <Spinner label={ta('cargando')} />}
      {mias.isError && <AvisoDeError error={mias.error} defecto={ta('error_cargar')} />}
      {mias.data && mias.data.length === 0 && (
        <EmptyState svgIcon={<Umbrella size={26} />} title={ta('sin_ausencias')} description={ta('sin_ausencias_texto')}
          ctaLabel={ta('pedir_ausencia')} onCta={onPedir} />
      )}
      {mias.data && mias.data.length > 0 && (
        <TablaSimple claseTabla="aus-tabla">
          <caption className="u-sr-only">{ta('tab_mias')}</caption>
          <thead><tr>
            <th scope="col">{ta('tipo')}</th><th scope="col">{ta('fechas')}</th><th scope="col">{ta('cantidad')}</th>
            <th scope="col">{ta('estado')}</th><th scope="col"><span className="u-sr-only">{ta('acciones')}</span></th>
          </tr></thead>
          <tbody>
            {mias.data.map(a => (
              <tr key={a.id}>
                <td><TipoChip a={a} /></td>
                <td><Pulsable type="button" className="aus-enlace" onClick={() => onAbrir(a.id)}>{fecha(a.start_date)} → {fecha(a.end_date)}</Pulsable></td>
                <td>{cantidad(a, ta)}</td>
                <td><EstadoDeAusenciaChip estado={a.status} />{a.status === 'waitlisted' && <ListOrdered size={13} aria-hidden />}</td>
                <td className="aus-acciones-fila">
                  <Button size="xs" variant="ghost" onClick={() => onAbrir(a.id)}>{ta('ver_detalle')}</Button>
                  {(a.status === 'pending' || a.status === 'waitlisted') && (
                    <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => onEditar(a)}>{ta('editar')}</Button>
                  )}
                  {a.status !== 'rejected' && a.status !== 'cancelled' && (
                    <Button size="xs" variant="ghost" icon={<X size={12} />} onClick={() => pedirCancelar(a)}>{ta('cancelar')}</Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
      {cancelar.isError && <AvisoDeError error={cancelar.error} defecto={ta('error_guardar')} />}
    </div>
  )
}
