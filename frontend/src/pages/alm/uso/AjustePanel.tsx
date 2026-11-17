/** Ajuste de nivel: propuestas de bajar de licencia con su ahorro y las reglas que las generan. */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownRight, Check, Coins, Layers3, Plus, Trash2, X } from 'lucide-react'
import { Button, DataTable, EmptyState, KpiCard, Modal, Section, Spinner, Select, Checkbox } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { confirmar, pedirTexto } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { useAppT } from '../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { licensesApi } from '../../../services/api'
import { almUsoApi } from '../../../services/api/almUso'
import type { PropuestaDeAjuste, ReglaDeNivel } from '../../../services/api/almUso'
import { fmtCurrency, fmtDate } from '../../../utils/helpers'
import { useErrorDeUso, useMoneda } from './comun'

/** Servicios que miden las fuentes integradas (claves de la evidencia). */
const SERVICIOS = ['apps_escritorio', 'exchange', 'onedrive', 'sharepoint', 'teams', 'skype', 'yammer', 'gmail', 'drive',
  'calendar', 'meet', 'docs', 'sso', 'inicio_de_sesion']

interface Borrador { id?: string; license_superior_id: string; license_inferior_id: string; servicios: string[]; notas: string; activa: boolean }

function EditorDeRegla({ borrador, onClose }: { borrador: Borrador; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const [b, setB] = useState<Borrador>(borrador)
  const { data: licencias = [] } = useQuery({ queryKey: ['alm-licencias-todas'], queryFn: () => licensesApi.list().then(r => r.data) })
  const guardar = useMutation({
    mutationFn: () => almUsoApi.guardarRegla({ license_superior_id: b.license_superior_id, license_inferior_id: b.license_inferior_id,
      servicios: b.servicios, notas: b.notas || null, activa: b.activa }, b.id),
    onSuccess: () => { toast.success(t('alm_uso.hecho')); qc.invalidateQueries({ queryKey: ['alm-uso-reglas'] })
      qc.invalidateQueries({ queryKey: ['alm-uso-propuestas'] }); onClose() },
    onError: fallo,
  })
  const alternar = (s: string) => setB(x => ({ ...x, servicios: x.servicios.includes(s) ? x.servicios.filter(y => y !== s) : [...x.servicios, s] }))
  return (
    <Modal open onClose={onClose} title={b.id ? t('alm_uso.editar_regla') : t('alm_uso.nueva_regla')} size="lg">
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <label className="almu-campo">{t('alm_uso.licencia_superior')}
            <Select suelto placeholder={false} className="alm-input" value={b.license_superior_id} onChange={e => setB({ ...b, license_superior_id: e.target.value })}>
              <option value="">{t('alm_uso.elige')}</option>
              {licencias.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </Select>
          </label>
          <label className="almu-campo">{t('alm_uso.licencia_inferior')}
            <Select suelto placeholder={false} className="alm-input" value={b.license_inferior_id} onChange={e => setB({ ...b, license_inferior_id: e.target.value })}>
              <option value="">{t('alm_uso.elige')}</option>
              {licencias.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </Select>
          </label>
        </div>
        <fieldset className="ds-grupo-opciones almu-servicios">
          <legend>{t('alm_uso.servicios_que_justifican')}</legend>
          <p className="u-text2-xs">{t('alm_uso.servicios_ayuda')}</p>
          <div className="almu-chips">
            {SERVICIOS.map(s => (
              <label key={s} className="almu-check">
                <Checkbox checked={b.servicios.includes(s)} onChange={() => alternar(s)} />
                {etiquetaCodigo(t, 'alm_uso.servicio', s)}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="almu-campo">{t('alm_uso.notas')}
          <input className="alm-input" value={b.notas} onChange={e => setB({ ...b, notas: e.target.value })} />
        </label>
        <label className="almu-check">
          <Checkbox checked={b.activa} onChange={(_, e) => setB({ ...b, activa: e.target.checked })} />{t('alm_uso.regla_activa')}
        </label>
        <div className="u-row-end almu-acciones">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardar.isPending} disabled={!b.license_superior_id || !b.license_inferior_id || !b.servicios.length}
            onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function AjustePanel() {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const moneda = useMoneda()
  const [editando, setEditando] = useState<Borrador | null>(null)
  const propuestas = useQuery({ queryKey: ['alm-uso-propuestas'], queryFn: () => almUsoApi.propuestas() })
  const reglas = useQuery({ queryKey: ['alm-uso-reglas'], queryFn: () => almUsoApi.reglas() })
  const decidir = useMutation({
    mutationFn: (d: { p: PropuestaDeAjuste; aceptar: boolean; motivo?: string }) =>
      almUsoApi.decidirAjuste({ nivel_id: d.p.nivel_id, assignment_id: d.p.assignment_id, aceptar: d.aceptar, motivo: d.motivo }),
    onSuccess: () => { toast.success(t('alm_uso.hecho')); qc.invalidateQueries({ queryKey: ['alm-uso-propuestas'] })
      qc.invalidateQueries({ queryKey: ['alm-uso-panel'] }) },
    onError: fallo,
  })
  const borrar = useMutation({
    mutationFn: (id: string) => almUsoApi.borrarRegla(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-uso-reglas'] }),
    onError: fallo,
  })
  const aceptar = async (p: PropuestaDeAjuste) => {
    if (await confirmar({ title: t('alm_uso.aceptar_ajuste_titulo'),
      message: t('alm_uso.aceptar_ajuste_msg', { quien: p.persona || p.equipo || '', superior: p.superior, inferior: p.inferior }),
      confirmLabel: t('alm_uso.aceptar') })) decidir.mutate({ p, aceptar: true })
  }
  const descartar = async (p: PropuestaDeAjuste) => {
    const motivo = await pedirTexto({ title: t('alm_uso.descartar'), message: t('alm_uso.descartar_ajuste_msg'),
      label: t('alm_uso.motivo_col'), multiline: true })
    if (motivo !== null) decidir.mutate({ p, aceptar: false, motivo })
  }
  const columnas: ColumnaDeTabla<PropuestaDeAjuste>[] = [
    { key: 'persona', label: t('alm_uso.titular'), render: (_v, p) => p.persona || p.equipo || '—' },
    { key: 'superior', label: t('alm_uso.cambio'), render: (_v, p) => (
      <span className="almu-cambio">{p.superior}<ArrowDownRight size={14} aria-label={t('alm_uso.a')} />{p.inferior}</span>
    ) },
    { key: 'servicios_usados', label: t('alm_uso.servicios_usados'), sortable: false,
      render: (_v, p) => p.servicios_usados.length ? p.servicios_usados.map(s => etiquetaCodigo(t, 'alm_uso.servicio', s)).join(', ') : t('alm_uso.ninguno') },
    { key: 'ultimo_uso', label: t('alm_uso.ultimo_uso'), render: (_v, p) => fmtDate(p.ultimo_uso) },
    { key: 'ahorro_anual', label: t('alm_uso.ahorro_anual'),
      render: (_v, p) => p.ahorro_anual == null ? t('alm_uso.sin_coste') : fmtCurrency(p.ahorro_anual, p.moneda) },
    { key: 'acciones', label: t('alm_uso.acciones'), sortable: false, render: (_v, p) => (
      <div className="almu-acciones">
        <Button size="xs" icon={<Check size={12} />} onClick={() => aceptar(p)}>{t('alm_uso.aceptar')}</Button>
        <Button size="xs" variant="ghost" icon={<X size={12} />} onClick={() => descartar(p)}>{t('alm_uso.descartar')}</Button>
      </div>
    ) },
  ]
  const columnasDeReglas: ColumnaDeTabla<ReglaDeNivel>[] = [
    { key: 'superior', label: t('alm_uso.licencia_superior') },
    { key: 'inferior', label: t('alm_uso.licencia_inferior') },
    { key: 'servicios', label: t('alm_uso.servicios_que_justifican'), sortable: false,
      render: (_v, r) => r.servicios.map(s => etiquetaCodigo(t, 'alm_uso.servicio', s)).join(', ') },
    { key: 'activa', label: t('alm_uso.estado_col'), render: (_v, r) => r.activa ? t('alm_uso.activa') : t('alm_uso.inactiva') },
    { key: 'acciones', label: t('alm_uso.acciones'), sortable: false, render: (_v, r) => (
      <div className="almu-acciones">
        <Button size="xs" variant="ghost" onClick={() => setEditando({ id: r.id, license_superior_id: r.license_superior_id,
          license_inferior_id: r.license_inferior_id, servicios: r.servicios, notas: r.notas ?? '', activa: r.activa })}>{t('common.edit')}</Button>
        <Button size="xs" variant="ghost" icon={<Trash2 size={12} />}
          onClick={async () => { if (await confirmar({ message: t('alm_uso.borrar_regla_msg'), danger: true })) borrar.mutate(r.id) }}>
          {t('common.delete')}
        </Button>
      </div>
    ) },
  ]
  const datos = propuestas.data
  return (
    <div className="u-stack-16">
      <p className="u-text2-sm">{t('alm_uso.ajuste_intro')}</p>
      {datos && (
        <div className="ds-grid-stats almu-kpis">
          <KpiCard icon={<Layers3 size={16} />} label={t('alm_uso.kpi_propuestas')} value={datos.items.length} accent />
          <KpiCard icon={<Coins size={16} />} label={t('alm_uso.kpi_ahorro_propuesto')} value={fmtCurrency(datos.ahorro_anual_total, moneda)}
            sub={t('alm_uso.ventana_dias', { n: datos.ventana_dias })} />
        </div>
      )}
      {propuestas.isLoading ? <Spinner /> : (datos?.items.length ?? 0) === 0 ? (
        <EmptyState svgIcon={<Layers3 size={28} aria-hidden="true" />} title={t('alm_uso.sin_propuestas')}
          description={(reglas.data?.reglas.length ?? 0) === 0 ? t('alm_uso.sin_reglas_desc') : t('alm_uso.sin_propuestas_desc')} />
      ) : <DataTable columns={columnas} data={datos?.items ?? []} />}
      <Section title={t('alm_uso.reglas_titulo')} subtitle={t('alm_uso.reglas_desc')}
        actions={<Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando({ license_superior_id: '', license_inferior_id: '',
          servicios: [], notas: '', activa: true })}>{t('alm_uso.nueva_regla')}</Button>}>
        {reglas.isLoading ? <Spinner /> : (
          <div className="u-stack-12">
            <DataTable columns={columnasDeReglas} data={reglas.data?.reglas ?? []} emptyTitle={t('alm_uso.sin_reglas')} />
            {(reglas.data?.sugerencias.length ?? 0) > 0 && (
              <div className="u-stack-8">
                <span className="u-text2-sm">{t('alm_uso.sugerencias_de_reglas')}</span>
                <div className="almu-chips">
                  {reglas.data?.sugerencias.map(s => (
                    <Button key={`${s.license_superior_id}-${s.license_inferior_id}`} size="xs" variant="secondary"
                      onClick={() => setEditando({ license_superior_id: s.license_superior_id, license_inferior_id: s.license_inferior_id,
                        servicios: [], notas: '', activa: true })}>
                      {t('alm_uso.sugerencia', { superior: s.superior, inferior: s.inferior })}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Section>
      {editando && <EditorDeRegla borrador={editando} onClose={() => setEditando(null)} />}
    </div>
  )
}
