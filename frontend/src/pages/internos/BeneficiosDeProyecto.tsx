/**
 * Clientes internos (22-11-2026): caso de negocio y beneficios de un proyecto
 * (`/internal-clients/projects/{pid}/benefits`): línea base, objetivo, real y %
 * de consecución. CRUD en la gestión; `ListaDeBeneficios` también se usa de
 * lectura en el portal interno. Ver docs/CLIENTES_INTERNOS.md §6.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Target, Trash2 } from 'lucide-react'
import { Button, EmptyState, IconButton, Input, Modal, Select, Spinner, TablaSimple, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { confirmar } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { projectsApi } from '../../services/api/projects'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import type { Beneficio, BeneficioIn } from '../../services/api/clientesInternos'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import type { Tono } from '../../utils/umbrales'
import { Semaforo, useOpcionesInternas, useT } from './comunes'
import { TIPOS_DE_BENEFICIO, etiquetaInterna, numeroONull, textoONull } from './logica'

/** Tono de la consecución (más es mejor): ≥ 100 % éxito, ≥ 70 % aviso, si no peligro. */
const tonoDeConsecucion = (pct: number | null): Tono | null => (pct == null ? null : pct >= 100 ? 'success' : pct >= 70 ? 'warning' : 'danger')

export function ListaDeBeneficios({ items, conProyecto = false, onEditar, onBorrar }: {
  items: Beneficio[]; conProyecto?: boolean; onEditar?: (b: Beneficio) => void; onBorrar?: (b: Beneficio) => void
}) {
  const t = useT()
  if (!items.length) return <p className="u-text2-sm">{t('internos.sin_beneficios')}</p>
  const n = (v: number | null, unidad: string | null) => (v == null ? '—' : `${fmtNumber(v, 2)}${unidad ? ` ${unidad}` : ''}`)
  return (
    <div className="u-scroll-x">
      <TablaSimple claseTabla="u-table" etiqueta={t('internos.beneficios')}>
        <thead>
          <tr>
            {[t('internos.beneficio'), ...(conProyecto ? [t('internos.col_proyecto')] : []), t('internos.col_tipo'), t('internos.linea_base'),
              t('internos.objetivo'), t('internos.real'), t('internos.consecucion'), t('internos.fecha_objetivo'), t('internos.col_responsable')].map(h => (
              <th key={h} scope="col" className="int-th">{h}</th>
            ))}
            {(onEditar || onBorrar) && <th scope="col" className="int-th"><span className="u-sr-only">{t('internos.acciones')}</span></th>}
          </tr>
        </thead>
        <tbody>
          {items.map(b => (
            <tr key={b.id}>
              <td className="int-td"><strong>{b.name}</strong>{b.notes && <div className="int-sub">{b.notes}</div>}</td>
              {conProyecto && <td className="int-td int-td--muted">{b.project_name || '—'}</td>}
              <td className="int-td"><StatusBadge kind="neutral" caps={false}>{etiquetaInterna(t, 'beneficio_', b.kind)}</StatusBadge></td>
              <td className="int-td int-td--num">{n(b.baseline, b.unit)}</td>
              <td className="int-td int-td--num">{n(b.target, b.unit)}</td>
              <td className="int-td int-td--num">{n(b.actual, b.unit)}</td>
              <td className="int-td"><Semaforo pct={b.achievement_pct} tono={tonoDeConsecucion(b.achievement_pct)} /></td>
              <td className="int-td int-td--muted">{b.target_date ? fmtDate(b.target_date) : '—'}</td>
              <td className="int-td int-td--muted">{b.owner_name || '—'}</td>
              {(onEditar || onBorrar) && (
                <td className="int-td">
                  <div className="u-row-6">
                    {onEditar && <IconButton ariaLabel={t('internos.editar')} title={t('internos.editar')} onClick={() => onEditar(b)}><Pencil size={14} aria-hidden /></IconButton>}
                    {onBorrar && <IconButton ariaLabel={t('internos.borrar')} title={t('internos.borrar')} onClick={() => onBorrar(b)}><Trash2 size={14} aria-hidden /></IconButton>}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </TablaSimple>
    </div>
  )
}

function FormularioDeBeneficio({ pid, item, onClose }: { pid: string; item: Beneficio | null; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const op = useOpcionesInternas()
  const txt = (v: number | string | null | undefined) => (v == null ? '' : String(v))
  const [f, setF] = useState<Record<string, string>>({
    name: item?.name || '', kind: item?.kind || 'ahorro', unit: item?.unit || '', baseline: txt(item?.baseline), target: txt(item?.target),
    actual: txt(item?.actual), target_date: item?.target_date || '', measured_at: item?.measured_at || '', owner_id: item?.owner_id || '', notes: item?.notes || '',
  })
  const set = (k: string) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  const guardar = useMutation({
    mutationFn: () => {
      const d: BeneficioIn = {
        name: f.name.trim(), kind: f.kind as BeneficioIn['kind'], unit: textoONull(f.unit), baseline: numeroONull(f.baseline), target: numeroONull(f.target),
        actual: numeroONull(f.actual), target_date: f.target_date || null, measured_at: f.measured_at || null, owner_id: f.owner_id || null, notes: textoONull(f.notes),
      }
      return item ? clientesInternosApi.editarBeneficio(item.id, d) : clientesInternosApi.crearBeneficio(pid, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['internal-clients', 'benefits', pid] }); toast.success(t('internos.guardado')); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} width={640} title={item ? t('internos.editar_beneficio') : t('internos.nuevo_beneficio')}>
      <div className="u-stack-8">
        <Input label={t('internos.beneficio')} required value={f.name} onChange={set('name')} />
        <div className="int-rejilla">
          <Select label={t('internos.col_tipo')} value={f.kind} placeholder={false} onChange={set('kind')}
            options={TIPOS_DE_BENEFICIO.map(k => ({ value: k, label: etiquetaInterna(t, 'beneficio_', k) }))} />
          <Input label={t('internos.unidad_medida')} value={f.unit} onChange={set('unit')} />
          <Input label={t('internos.linea_base')} type="number" step="any" value={f.baseline} onChange={set('baseline')} />
          <Input label={t('internos.objetivo')} type="number" step="any" value={f.target} onChange={set('target')} />
          <Input label={t('internos.real')} type="number" step="any" value={f.actual} onChange={set('actual')} />
          <Input label={t('internos.fecha_objetivo')} type="date" value={f.target_date} onChange={set('target_date')} />
          <Input label={t('internos.medido_el')} type="date" value={f.measured_at} onChange={set('measured_at')} />
          <Select label={t('internos.col_responsable')} value={f.owner_id} onChange={set('owner_id')} placeholder={t('internos.sin_asignar')}
            options={op.users.map(u => ({ value: u.id, label: u.full_name }))} />
        </div>
        <Textarea label={t('internos.notas')} value={f.notes} onChange={set('notes')} rows={2} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.name.trim() || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function BeneficiosDeProyecto() {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [pid, setPid] = useState('')
  const [editando, setEditando] = useState<Beneficio | null | 'nuevo'>(null)
  const { data: proyectos = [] } = useQuery({
    queryKey: ['projects', 'para-beneficios'],
    queryFn: () => projectsApi.list().then(r => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['internal-clients', 'benefits', pid],
    queryFn: () => clientesInternosApi.beneficios(pid),
    enabled: !!pid,
  })
  const borrar = useMutation({
    mutationFn: (id: string) => clientesInternosApi.borrarBeneficio(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['internal-clients', 'benefits', pid] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="u-stack-8">
      <div className="int-barra">
        <div className="int-barra__filtros">
          <Select label={t('internos.col_proyecto')} value={pid} onChange={e => setPid(e.target.value)} placeholder={t('internos.elegir')}
            options={proyectos.map(p => ({ value: String(p.id), label: p.code ? `${p.code} · ${p.name}` : String(p.name) }))} />
        </div>
        {pid && <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('internos.nuevo_beneficio')}</Button>}
      </div>
      {!pid ? (
        <EmptyState icon={<Target size={28} />} title={t('internos.elige_proyecto')} description={t('internos.beneficios_d')} />
      ) : isLoading ? <Spinner /> : (
        <ListaDeBeneficios items={items} onEditar={setEditando}
          onBorrar={async b => { if (await confirmar({ message: t('internos.borrar_confirmar', { titulo: b.name }), danger: true })) borrar.mutate(b.id) }} />
      )}
      {editando && pid && <FormularioDeBeneficio pid={pid} item={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  )
}
