/**
 * Pestaña de plantillas de proyecto: alta, instanciación y borrado.
 * Troceado de ProjectsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useId } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, templatesApi } from '../../services/api'
import type { PlantillaDeProyecto } from '../../services/api/tipos-proyectos'
import { Button, Modal, Spinner, EmptyState, ClientSelect, Pulsable, Select, Input, Textarea } from '../../components/ui'
import { Plus, ClipboardList, Clock, CalendarDays, Building2, Code2, Wrench, FlaskConical, Home, Layers } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAppT } from '../../i18n/AppLangContext'
import DateInput from '../../components/ui/DateInput'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import type { NewTemplate, InstantiateForm } from './compartido'

// ── Templates Tab ─────────────────────────────────────────────────────────────
export function TemplatesTab() {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [instantiating, setInstantiating] = useState<PlantillaDeProyecto | null>(null)
  const [instForm, setInstForm] = useState<InstantiateForm>({ name:'', client_id:'', client_name:'', start_date: new Date().toISOString().slice(0,10), budget_amount:'' })

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => templatesApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery({ queryKey: ['users', 'directory'], queryFn: () => usersApi.directory().then(r => r.data) })
  const pms = users.filter(u => ['admin','pm'].includes(u.role))

  const { mutate: instantiate, isPending: creating } = useMutation({
    mutationFn: ({ tplId, data }: { tplId: string; data: Omit<InstantiateForm, 'budget_amount'> & { budget_amount?: number } }) => templatesApi.instantiate(tplId, data).then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success(traducir('proyectos_ui.proyecto_creado', { codigo: data.project_code, nombre: data.project_name, fases: data.phases_created, tareas: data.tasks_created }))
      setInstantiating(null)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [newTpl, setNewTpl] = useState<NewTemplate>({ name:'', description:'', project_type:'consulting', estimated_weeks:12, phases:[{name:traducir('proyectos_ui.fase_1'),estimated_weeks:4,tasks:[{title:traducir('proyectos_ui.tarea_inicial'),estimated_hours:8}]}] })

  const { mutate: createTpl, isPending: creatingTpl } = useMutation({
    mutationFn: (d: NewTemplate) => templatesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-templates'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const TPL_ICONS: Record<string, LucideIcon> = { consulting: Building2, development: Code2, maintenance: Wrench, rd: FlaskConical, internal: Home }

  return (
    <div>
      <div className="prj-row-12">
        <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('projects.nueva_plantilla')}</Button>
      </div>

      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState svgIcon={<ClipboardList size={36} />} title={traducir('projects.sin_plantillas')} description={traducir('proyectos_ui.sin_plantillas_desc')} />
      ) : (
        <div className="prj-grid-4">
          {templates.map(t => (
            <div className="prj-card prj-box-7" key={t.id}>
              <div className="prj-row-13">
                {(() => { const IconoTipo = TPL_ICONS[t.project_type] || ClipboardList; return <IconoTipo size={22} className="prj-icono-plantilla" aria-hidden /> })()}
                <div className="u-flex1">
                  <div className="u-md-700">{t.name}</div>
                  {t.description && <div className="u-text2-sm-mt2">{t.description}</div>}
                </div>
              </div>

              <div className="prj-row-muted-2">
                <span className="prj-dato-icono"><CalendarDays size={12} aria-hidden /> {traducir('proyectos_ui.n_semanas', { n: t.estimated_weeks || '?' })}</span>
                <span className="prj-dato-icono"><Clock size={12} aria-hidden /> {traducir('proyectos_ui.n_horas_estimadas', { n: t.estimated_hours || '?' })}</span>
                <span className="prj-dato-icono"><Layers size={12} aria-hidden /> {traducir('proyectos_ui.n_fases', { n: t.phases?.length || 0 })}</span>
              </div>

              {t.phases?.slice(0,3).map((ph, i) => (
                <div className="prj-box-8" key={ph.id}>
                  <span className="u-text2">{i+1}.</span> <span className="u-text1">{ph.name}</span>
                  <span className="prj-text-muted">{traducir('proyectos_ui.n_semanas_abrev', { n: ph.estimated_weeks ?? '?' })} · {traducir('proyectos_ui.n_tareas', { n: ph.tasks.length })}</span>
                </div>
              ))}
              {(t.phases?.length||0) > 3 && <div className="u-hint">+{t.phases.length-3} {traducir('projects.fases_mas')}</div>}

              <Pulsable className="prj-btn-base-2" onClick={() => { setInstantiating(t); setInstForm({ name:`${t.name} — ${new Date().getFullYear()}`, client_id:'', client_name:'', start_date:new Date().toISOString().slice(0,10), budget_amount:'', pm_id:'' }) }}>
                {traducir('projects.crear_proyecto_desde_esta_plantilla')}
              </Pulsable>
            </div>
          ))}
        </div>
      )}

      {instantiating && (
        <Modal open title={traducir('proyectos_ui.crear_proyecto_titulo', { nombre: instantiating.name })} onClose={() => setInstantiating(null)} width={520}>
          <div className="u-stack-14">
            <div className="prj-card-muted-2">
              {traducir('projects.esta_plantilla_creara')} <strong className="u-text1">{traducir('proyectos_ui.n_fases', { n: instantiating.phases?.length || 0 })}</strong> {traducir('proyectos_ui.y_aproximadamente')} <strong className="u-text1">{traducir('proyectos_ui.n_tareas', { n: instantiating.phases?.reduce((s: number, p) => s + (p.tasks?.length || 0), 0) || 0 })}</strong> {traducir('projects.automaticamente')}
            </div>
            <Input label={traducir('projects.nombre_del_proyecto_2')} id={`${idCampo}-1`} value={instForm.name} onChange={e => setInstForm(f=>({...f,name:e.target.value}))} />
            <div className="u-grid2-14">
              <ClientSelect label={traducir('proyectos_ui.cliente')} id={`${idCampo}-cliente`} value={instForm.client_id||''} onChange={(id, c) => setInstForm(f=>({...f, client_id: id, client_name: c ? c.name : ''}))} placeholder={traducir('projects.selecciona_un_cliente')} />
              <DateInput label={traducir('projects.label_start_date')} id={`${idCampo}-2`} value={instForm.start_date} onChange={e => setInstForm(f=>({...f,start_date:e.target.value}))} />
              <Input label={traducir('proyectos_ui.presupuesto_moneda', { moneda: fmtMoneda.simbolo })} id={`${idCampo}-3`} type="number" value={instForm.budget_amount} onChange={e => setInstForm(f=>({...f,budget_amount:e.target.value}))} />
              <Select label={traducir('proyectos_ui.project_manager')} placeholder={false} id={`${idCampo}-4`} value={instForm.pm_id||''} onChange={e => setInstForm(f=>({...f,pm_id:e.target.value}))}>
                  <option value="">{traducir('projects.sin_asignar')}</option>
                  {pms.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </Select>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setInstantiating(null)}>{traducir('common.cancel')}</Button>
              <Button onClick={() => instantiate({ tplId: instantiating.id, data: { ...instForm, budget_amount: instForm.budget_amount ? +instForm.budget_amount : undefined } })} disabled={creating || !instForm.name}>
                {creating ? traducir('proyectos_ui.creando') : traducir('proyectos_ui.crear_proyecto_btn')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {showCreate && (
        <Modal open title={traducir('projects.nueva_plantilla_2')} onClose={() => setShowCreate(false)} width={580}>
          <div className="u-stack-14">
            <Input label={traducir('proyectos_ui.nombre_req')} id={`${idCampo}-nombre`} value={newTpl.name} onChange={e => setNewTpl(f=>({...f,name:e.target.value}))} placeholder={traducir('projects.nombre_de_la_plantilla')} aria-label={traducir('projects.nombre_de_la_plantilla')} />
            <Textarea label={traducir('projects.label_description')} id={`${idCampo}-5`} value={newTpl.description||''} onChange={e => setNewTpl(f=>({...f,description:e.target.value}))} rows={2} />
            <div className="prj-grid-5">
              <Select label={traducir('proyectos_ui.col_tipo')} placeholder={false} id={`${idCampo}-6`} value={newTpl.project_type} onChange={e => setNewTpl(f=>({...f,project_type:e.target.value}))}>
                  {['consulting','development','maintenance','rd','internal'].map(t => <option key={t} value={t}>{t}</option>)}
                </Select>
              <Input label={traducir('proyectos_ui.semanas_estimadas')} id={`${idCampo}-7`} type="number" value={newTpl.estimated_weeks} onChange={e => setNewTpl(f=>({...f,estimated_weeks:+e.target.value}))} />
              <Input label={traducir('proyectos_ui.horas_estimadas')} id={`${idCampo}-8`} type="number" value={newTpl.estimated_hours||''} onChange={e => setNewTpl(f=>({...f,estimated_hours:+e.target.value}))} />
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{traducir('common.cancel')}</Button>
              <Button onClick={() => createTpl(newTpl)} disabled={creatingTpl || !newTpl.name}>{traducir('proyectos_ui.crear_plantilla')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
