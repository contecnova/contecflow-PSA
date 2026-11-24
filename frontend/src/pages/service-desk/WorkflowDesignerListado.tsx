// Listado de blueprints del disenador de flujos y sus modales (clonar, confirmar, crear, plantillas). 23-11-2026: troceado de WorkflowDesignerPage sin cambio de comportamiento.
import { useMemo, useState, useId } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, Plus, Trash2, Copy } from 'lucide-react'
import { sdWorkflowDesignerApi, type ApiError } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Buscador, Button, Spinner, StatusBadge, Modal, EmptyState, Pulsable, Select, Input, Textarea } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { type Blueprint, type ErrorDeFlujo, PROCESOS, type PlantillaFlujo, mensajeDelDetalle, nombreDeNodo, nombreDeProceso } from './WorkflowDesignerComun'

// ── Listado de blueprints ────────────────────────────────────────────────────
export function BlueprintList({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [cloneTarget, setCloneTarget] = useState<{ id: string; name: string } | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<{ id: string; name: string } | null>(null)

  const { data: blueprints = [], isLoading } = useQuery({
    queryKey: ['sd-wf-blueprints', filter],
    queryFn: () => sdWorkflowDesignerApi.blueprints(filter ? { process_type: filter } : undefined).then(r => r.data),
  })

  const archive = useMutation({
    mutationFn: (id: string) => sdWorkflowDesignerApi.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_archivado'))
    },
    onError: (e: ApiError) => toast.error(extractErr(e, traducir('workflowdesigner.error_archivar'))),
  })

  const clone = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => sdWorkflowDesignerApi.clone(id, { name }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_clonado'))
      onOpen(r.data.id)
    },
    onError: (e: ApiError) => toast.error(extractErr(e, traducir('workflowdesigner.error_clonar'))),
  })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return blueprints
    return blueprints.filter(b =>
      (b.name || '').toLowerCase().includes(q) ||
      (b.description || '').toLowerCase().includes(q),
    )
  }, [blueprints, search])

  return (
    <>
      {/* Toolbar */}
      <div className="ds-toolbar">
        <Buscador className="wfd-search" aria-label={traducir('workflowdesigner.buscar')} value={search} onChange={setSearch} placeholder={traducir('workflowdesigner.buscar')} />
        <Select suelto placeholder={false} value={filter} onChange={e => setFilter(e.target.value)} aria-label={traducir('workflowdesigner.tipo_de_proceso')}
          className="wfd-filter">
          <option value="">{traducir('workflowdesigner.todos_los_procesos')}</option>
          {PROCESOS.map(p => <option key={p} value={p}>{nombreDeProceso(p, traducir)}</option>)}
        </Select>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="wfd-loading-flex"><Spinner /></div>
      ) : filtered.length === 0 ? (
        <EmptyState icon={<GitBranch size={28} />}
          title={search || filter ? traducir('workflowdesigner.no_coinciden') : traducir('workflowdesigner.aun_no_hay')}
          description={search || filter ? traducir('workflowdesigner.prueba_otros') : traducir('workflowdesigner.crea_uno')}
          action={search || filter ? undefined : (
            <Button icon={<Plus size={14} />} onClick={onNew}>{traducir('workflowdesigner.nuevo_blueprint')}</Button>
          )} />
      ) : (
        <div className="ds-grid-cards">
          {filtered.map(bp => (
            <BlueprintCard key={bp.id} bp={bp}
              onOpen={() => onOpen(bp.id)}
              onClone={() => setCloneTarget({ id: bp.id, name: bp.name })}
              onArchive={() => setArchiveTarget({ id: bp.id, name: bp.name })}
            />
          ))}
        </div>
      )}

      {cloneTarget && (
        <CloneBlueprintModal
          bp={cloneTarget}
          onClose={() => setCloneTarget(null)}
          onConfirm={(name: string) => { setCloneTarget(null); clone.mutate({ id: cloneTarget.id, name }) }}
        />
      )}
      {archiveTarget && (
        <ConfirmModal
          title={traducir('workflowdesigner.archivar_titulo')}
          message={traducir('workflowdesigner.confirmar_archivar', { name: archiveTarget.name })}
          confirmLabel={traducir('workflowdesigner.archivar')}
          onClose={() => setArchiveTarget(null)}
          onConfirm={() => { setArchiveTarget(null); archive.mutate(archiveTarget.id) }}
        />
      )}
    </>
  )
}

function BlueprintCard({ bp, onOpen, onClone, onArchive }: { bp: Blueprint; onOpen: () => void; onClone: () => void; onArchive: () => void }) {
  const { t: traducir } = useAppLang()
  const statusKind = bp.status === 'published' ? 'success'
                    : bp.status === 'draft' ? 'warning' : 'neutral'
  const statusLabel = bp.status === 'published' ? traducir('workflowdesigner.st_published')
                     : bp.status === 'draft' ? traducir('workflowdesigner.st_draft') : traducir('workflowdesigner.st_archived')
  return (
    <div role="button" tabIndex={0}
      className="ds-card ds-card--clickable"
      onClick={onOpen}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}
    >
      <div className="ds-row-between wfd-card-top">
        <div className="u-min0">
          <div className="wfd-card-name">{bp.name}</div>
          {bp.description && (
            <div className="ds-muted wfd-card-desc">
              {bp.description}
            </div>
          )}
        </div>
        <StatusBadge kind={statusKind}>{statusLabel}</StatusBadge>
      </div>
      <div className="ds-row u-text2-xs">
        <span className="wfd-tag">
          {nombreDeProceso(bp.process_type, traducir)}
        </span>
        <span>v{bp.latest_version}</span>
        {bp.published_version && <span className="u-success">· {traducir('workflowdesigner.publicada_v', { n: bp.published_version })}</span>}
      </div>
      <div className="ds-row"
        role="presentation"
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}>
        <Button size="sm" variant="secondary" icon={<Copy size={12} />} onClick={onClone}>{traducir('workflowdesigner.clonar')}</Button>
        <Button size="sm" variant="secondary" icon={<Trash2 size={12} />} onClick={onArchive}>{traducir('workflowdesigner.archivar')}</Button>
      </div>
    </div>
  )
}

function CloneBlueprintModal({ bp, onClose, onConfirm }: { bp: { name: string }; onClose: () => void; onConfirm: (name: string) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [name, setName] = useState(traducir('workflowdesigner.copia', { name: bp.name }))
  return (
    <Modal open width={480} title={traducir('workflowdesigner.clonar_titulo')} onClose={onClose}>
      <div className="u-stack-12">
        <Input label={traducir('workflowdesigner.nombre_de_la_copia')} id={`${idCampo}-1`} autoFocus value={name} onChange={e => setName(e.target.value)} />
        <div className="wfd-actions">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button onClick={() => onConfirm(name.trim())} disabled={!name.trim()}>{traducir('workflowdesigner.clonar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function ConfirmModal({ title, message, confirmLabel, onClose, onConfirm }: { title: string; message: string; confirmLabel?: string; onClose: () => void; onConfirm: () => void }) {
  const { t: traducir } = useAppLang()
  return (
    <Modal open width={480} title={title} onClose={onClose}>
      <div className="u-stack-16">
        <p className="wfd-confirm-text">{message}</p>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button onClick={onConfirm}>{confirmLabel ?? traducir('workflowdesigner.confirmar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export function CreateBlueprintModal({ onClose, onCreated }: { onClose: () => void; onCreated?: (bp: Blueprint) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [processType, setProcessType] = useState('ticket')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => sdWorkflowDesignerApi.createBlueprint({
      name, process_type: processType, description: description || null,
      graph: {
        nodes: [
          { id: 'start_1', type: 'start', position: { x: 100, y: 200 }, data: { label: nombreDeNodo('start', traducir) } },
          { id: 'end_1', type: 'end', position: { x: 500, y: 200 }, data: { label: nombreDeNodo('end', traducir) } },
        ],
        edges: [{ id: 'e1', source: 'start_1', target: 'end_1', branch: 'next' }],
      },
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_creado'))
      onCreated?.(r.data)
    },
    onError: (e: ErrorDeFlujo) => toast.error(mensajeDelDetalle(e?.response?.data?.detail) || extractErr(e, traducir('workflowdesigner.error'))),
  })

  return (
    <Modal open width={480} title={traducir('workflowdesigner.nuevo_blueprint')} onClose={onClose}>
      <div className="u-stack-12">
        <Input label={traducir('workflowdesigner.nombre')} id={`${idCampo}-1`} autoFocus value={name} onChange={e => setName(e.target.value)} placeholder={traducir('workflowdesigner.p_ej_triaje_de_incidentes')} />
        <Select label={traducir('workflowdesigner.tipo_de_proceso')} placeholder={false} id={`${idCampo}-2`} value={processType} onChange={e => setProcessType(e.target.value)}>
            {PROCESOS.map(p => <option key={p} value={p}>{nombreDeProceso(p, traducir)}</option>)}
          </Select>
        <Textarea label={traducir('workflowdesigner.descripcion_opcional')} id={`${idCampo}-3`} rows={3} value={description} onChange={e => setDescription(e.target.value)} />
        <div className="wfd-actions">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button onClick={() => create.mutate()} disabled={!name.trim()} loading={create.isPending}>
            {traducir('workflowdesigner.crear_y_abrir')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function TemplatePickerModal({ onClose, onPicked }: { onClose: () => void; onPicked?: (bp: Blueprint) => void }) {
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['sd-wf-templates'],
    queryFn: () => sdWorkflowDesignerApi.templates().then(r => r.data),
  })

  const useTemplate = useMutation({
    mutationFn: (tpl: PlantillaFlujo) => sdWorkflowDesignerApi.createBlueprint({
      name: tpl.name, process_type: tpl.process_type, description: tpl.description,
      graph: tpl.graph,
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_creado_plantilla'))
      onPicked?.(r.data)
    },
    onError: (e: ErrorDeFlujo) => toast.error(mensajeDelDetalle(e?.response?.data?.detail) || traducir('workflowdesigner.error_crear')),
  })

  return (
    <Modal open title={traducir('workflowdesigner.elegir_plantilla')} onClose={onClose} width={620}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-8">
          {templates.map(tpl => (
            <Pulsable key={tpl.id} onClick={() => useTemplate.mutate(tpl)}
              className="wfd-tpl"
            >
              <div className="wfd-tpl__head">
                <span className="wfd-bold">{tpl.name}</span>
                <span className="wfd-tpl__tag">
                  {nombreDeProceso(tpl.process_type, traducir)}
                </span>
              </div>
              <div className="u-text2-xs">{tpl.description}</div>
              <div className="u-hint">
                {traducir('workflowdesigner.nodos_aristas', { n: tpl.graph.nodes.length, m: tpl.graph.edges.length })}
              </div>
            </Pulsable>
          ))}
        </div>
      )}
    </Modal>
  )
}
