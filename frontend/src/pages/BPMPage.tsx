import { BPMN_TARGET_NAMESPACE } from '../constants/bpmn'
import { xmlEsc } from './bpm/generadorBpmn'
import { cargarTextosCatalogo, construirCatalogo } from './bpm/catalogo'
import { textoErrorDeInstancia } from './bpm/textos'
import type { ProcesoCatalogo } from './bpm/catalogo'
import { useState, useEffect, useRef, useMemo, useId } from 'react'
import type { CSSProperties, RefObject } from 'react'
import type BaseViewer from 'bpmn-js/lib/BaseViewer'
import type { BaseViewerOptions } from 'bpmn-js/lib/BaseViewer'
import type Canvas from 'diagram-js/lib/core/Canvas'
import { Button, Page, Tabs, EmptyState, IconButton, Pulsable, Select } from '../components/ui'
import { Network, Plus, X, ChevronLeft, ChevronRight, Edit3, Download, Search, Play, History, Trash2, Archive, User, Timer, ListOrdered, LayoutGrid, Activity, Workflow, SearchX, Save } from 'lucide-react'
import BpmRunPanel from './bpm/BpmRunPanel'
import BpmVersionsModal, { BpmProblemsModal } from './bpm/BpmVersionsModal'
import { bpmnProcessesApi, apiErrorMsg } from '../services/api'
import type { ProblemaBpmn, ProcesoBpmn } from '../services/api/tipos-documentos'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useConfirm } from '../context/ConfirmContext'
import { useAppLang } from '../i18n/AppLangContext'
import './BPMPage.css'

// Revisión BPM 2026-11-16 (ver DOCS.md, «Revisión BPM (16-11-2026)»):
// - el listado trae el XML en una sola petición (`include_xml`): antes, una
//   petición de detalle por proceso;
// - lo que se ve es lo que se ejecuta: iniciar un proceso del catálogo crea (o
//   actualiza, si era el esqueleto sembrado sin editar) su registro con el
//   diagrama mostrado; antes había que editarlo y guardarlo, y un proceso
//   sembrado ejecutaba el esqueleto lineal en castellano y no el diagrama visto;
// - antes de iniciar se valida y los problemas salen traducidos;
// - versiones y publicación, borrar y archivar, con los permisos de la API
//   (admin y PM editan; team lead ve y sigue la ejecución);
// - un diagrama que no se puede abrir lo dice, en vez de quedarse en blanco.

// NOTE: bpmn-js (JS + CSS) is loaded dynamically inside useBpmnViewer so it
// stays out of the initial bundle (~400 KB JS + assets). See audit #43, #81.
let _bpmnCssLoaded = false
async function loadBpmnCssOnce() {
  if (_bpmnCssLoaded) return
  _bpmnCssLoaded = true
  await Promise.all([
    import('bpmn-js/dist/assets/diagram-js.css'),
    import('bpmn-js/dist/assets/bpmn-font/css/bpmn.css'),
  ])
}

// ─── PROCESS CATALOG ─────────────────────────────────────────────────────────
const CATEGORIES = [
  { id: 'all',        labelKey: 'bpm.cat_all',         color: 'var(--accent)' },
  { id: 'proyectos',  labelKey: 'bpm.cat_proyectos',   color: 'var(--accent)' },
  { id: 'finanzas',   labelKey: 'bpm.cat_finanzas',    color: 'var(--success)' },
  { id: 'rrhh',       labelKey: 'bpm.cat_rrhh',        color: 'var(--warning)' },
  { id: 'servicedesk',labelKey: 'bpm.cat_servicedesk', color: 'var(--danger)' },
  { id: 'crm',        labelKey: 'bpm.cat_crm',         color: 'var(--purple)' },
  { id: 'admin',      labelKey: 'bpm.cat_admin',       color: 'var(--text-3)' },
]

const CAT_COLOR = Object.fromEntries(CATEGORIES.map(c => [c.id, c.color]))


// ─── BPMN VIEWER HOOK ────────────────────────────────────────────────────────
function useBpmnViewer(containerRef: RefObject<HTMLDivElement | null>, xml: string | null, editMode: boolean) {
  const instanceRef = useRef<BaseViewer | null>(null)
  const [errorImport, setErrorImport] = useState(false)

  useEffect(() => {
    setErrorImport(false)
    if (!containerRef.current || !xml) return

    const init = async () => {
      if (instanceRef.current) {
        try { instanceRef.current.destroy() } catch {}
        instanceRef.current = null
      }

      // Dynamic import: keeps bpmn-js (~400 KB) and its CSS out of the
      // initial bundle. CSS is loaded once, lazily, in parallel with the
      // JS module.
      await loadBpmnCssOnce()

      let BpmnClass: new (options?: BaseViewerOptions) => BaseViewer
      if (editMode) {
        const mod = await import('bpmn-js/lib/Modeler')
        BpmnClass = mod.default
      } else {
        const mod = await import('bpmn-js')
        BpmnClass = mod.default
      }

      const instance = new BpmnClass({ container: containerRef.current })
      instanceRef.current = instance

      try {
        await instance.importXML(xml)
        const canvas = instance.get<Canvas>('canvas')
        // Con 'fit-viewport' el centro solo actúa como indicador (centrar o no):
        // diagram-js comprueba si es truthy. Antes se pasaba 'auto'.
        canvas.zoom('fit-viewport', { x: 0, y: 0 })
      } catch (err) {
        console.error('BPMN import error:', err)
        setErrorImport(true)
      }
    }

    init()

    return () => {
      if (instanceRef.current) {
        try { instanceRef.current.destroy() } catch {}
        instanceRef.current = null
      }
    }
  }, [xml, editMode, containerRef])

  const getXml = async () => {
    if (!instanceRef.current) return null
    try {
      const { xml: exported } = await instanceRef.current.saveXML({ format: true })
      return exported
    } catch { return null }
  }

  return { getXml, errorImport }
}

// ─── BLANK BPMN TEMPLATE ─────────────────────────────────────────────────────
const BLANK_BPMN_PLANTILLA = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  id="Definitions_new" targetNamespace="${BPMN_TARGET_NAMESPACE}">
  <bpmn:process id="Process_new" name="{{proceso}}" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" name="{{inicio}}">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:task id="Task_1" name="{{actividad}}">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:task>
    <bpmn:endEvent id="EndEvent_1" name="{{fin}}">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_new">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="152" y="82" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_1_di" bpmnElement="Task_1">
        <dc:Bounds x="250" y="60" width="100" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="412" y="82" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_1_di" bpmnElement="Flow_1">
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="188" y="100" />
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="250" y="100" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_2_di" bpmnElement="Flow_2">
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="350" y="100" />
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="412" y="100" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`

/** Diagrama en blanco con sus tres nodos de ejemplo en el idioma de la interfaz. */
function blankBpmn(traducir: (k: string) => string, nombre: string): string {
  return BLANK_BPMN_PLANTILLA
    .replace('{{proceso}}', xmlEsc(nombre || traducir('bpm.blank_proceso')))
    .replace('{{inicio}}', xmlEsc(traducir('bpm.blank_inicio')))
    .replace('{{actividad}}', xmlEsc(traducir('bpm.blank_actividad')))
    .replace('{{fin}}', xmlEsc(traducir('bpm.blank_fin')))
}

// ─── STYLES ───────────────────────────────────────────────────────────────────
// Las clases viven en BPMPage.css. El color de categoría es un dato: se pasa
// como propiedad CSS (`--bpmp-cat` / `--bpmp-tag`) que consumen las clases.
const catVar = (name: '--bpmp-cat' | '--bpmp-tag', color: string): CSSProperties => ({ [name]: color } as CSSProperties)

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
type BackendProcess = ProcesoBpmn
type Process = {
  id: string
  category: string
  name: string
  description: string
  owner?: string
  sla?: string
  steps?: string[]
  bpmn: string
  isCustom?: boolean
  _backendId?: string
  _version?: number
  /** Versión publicada (la que se ejecuta); null: se ejecuta la última. */
  _published?: number | null
  _status?: ProcesoBpmn['status']
  /** Registro sembrado por el backend sin editar: su diagrama es un esqueleto lineal, no el que se muestra. */
  _esqueleto?: boolean
}
type NewProcess = { name: string; category: string; description: string; owner: string; sla: string }

export default function BPMPage(): JSX.Element {
  const idCampo = useId()
  const { t: traducir, lang } = useAppLang()
  const { hasRole } = useAuth()
  const { confirmar } = useConfirm()
  // La API exige admin o PM para crear, guardar, publicar, iniciar y borrar.
  const puedeEditar = hasRole('admin', 'pm')
  // Catálogo del sistema en el idioma activo: la estructura es fija y los
  // textos llegan con import() por idioma (ver ./bpm/catalogo).
  const [catalogo, setCatalogo] = useState<{ lang: string; procesos: ProcesoCatalogo[] } | null>(null)
  useEffect(() => {
    let vigente = true
    cargarTextosCatalogo(lang).then(({ lang: cargado, textos, lineales }) => {
      if (vigente) setCatalogo({ lang: cargado, procesos: construirCatalogo(textos, traducir, lineales) })
    }).catch(e => {
      console.warn('[BPM] catalogue texts failed:', e)
      // Sin textos del catálogo se muestran al menos los procesos propios.
      if (vigente) { setCatalogo({ lang, procesos: [] }); setErrorCarga(true) }
    })
    return () => { vigente = false }
    // `traducir` cambia con el idioma; el efecto ya depende de `lang`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang])
  const PROCESS_CATALOG = useMemo<ProcesoCatalogo[]>(() => catalogo?.procesos ?? [], [catalogo])
  const [selectedCat, setSelectedCat]         = useState('all')
  const [selectedProcess, setSelectedProcess] = useState<Process | null>(null)
  const [editMode, setEditMode]               = useState(false)
  const [showAddForm, setShowAddForm]         = useState(false)
  // Grouped backend data: list of records (custom + catalogue overrides) and
  // a key->latestXML map. They're updated together after reloadBackend(); the
  // XML map is also patched in-place when a process is saved or created.
  const [backend, setBackend]                 = useState<{ processes: BackendProcess[]; xmlByKey: Record<string, string> }>({ processes: [], xmlByKey: {} })
  const { processes: backendProcesses, xmlByKey: versionXmlByKey } = backend
  const [newProcess, setNewProcess]           = useState<NewProcess>({ name: '', category: 'proyectos', description: '', owner: '', sla: '' })
  const [search, setSearch]                   = useState('')
  const [saving, setSaving]                   = useState(false)
  const [errorCarga, setErrorCarga]           = useState(false)
  const [verVersiones, setVerVersiones]       = useState(false)
  // Una versión anterior abierta desde «Versiones» (solo lectura).
  const [versionAbierta, setVersionAbierta]   = useState<{ version: number; xml: string } | null>(null)
  const [problemas, setProblemas]             = useState<ProblemaBpmn[] | null>(null)
  const [iniciando, setIniciando]             = useState(false)
  // Auditoría 2026-11: además del catálogo, la ejecución (bandeja e instancias).
  const [view, setView]                       = useState<'catalog' | 'run'>('catalog')
  const containerRef                          = useRef<HTMLDivElement>(null)
  const toast                                 = useToast()

  // ── Load backend processes (custom + catalogue overrides) ────────────────
  const reloadBackend = async () => {
    try {
      // Una sola petición con el XML de la última versión de cada proceso.
      const r = await bpmnProcessesApi.list({ include_inactive: false, include_xml: true })
      const list = r.data
      const xmlByKey: Record<string, string> = {}
      list.forEach(p => { if (p.latest_xml) xmlByKey[p.key] = p.latest_xml })
      setBackend({ processes: list, xmlByKey })
      setErrorCarga(false)
    } catch (e) {
      // El catálogo del sistema se sigue viendo; los procesos guardados no.
      console.warn('[BPM] backend load failed:', e)
      setErrorCarga(true)
    }
  }
  useEffect(() => { reloadBackend() }, [])

  // Merge: catalogue (with backend XML override if present) + custom backend processes
  const allProcesses = useMemo<Process[]>(() => {
    // Hasta tener los textos del catálogo no se pinta nada: si no, los registros
    // sembrados del backend saldrían un instante como procesos propios.
    if (!catalogo) return []
    const catalogIds = new Set(PROCESS_CATALOG.map(p => p.id))
    const overriddenCatalog = PROCESS_CATALOG.map(p => {
      const ov = backendProcesses.find(b => b.key === p.id)
      // Un registro sembrado y sin editar (versión 1) es un esqueleto lineal en
      // castellano generado por el backend: el diagrama traducido del catálogo
      // manda. Una edición del usuario crea la versión 2 y esa sí se respeta.
      const sembradoSinEditar = !!ov?.is_seeded && (ov.latest_version || 1) <= 1
      const xml = sembradoSinEditar ? undefined : versionXmlByKey[p.id]
      return {
        ...p, bpmn: xml || p.bpmn, _backendId: ov?.id, _version: ov?.latest_version || 1,
        _published: ov?.published_version ?? null, _status: ov?.status, _esqueleto: sembradoSinEditar,
      }
    })
    const customs = backendProcesses
      .filter(b => !catalogIds.has(b.key))
      .map(b => ({
        id: b.key,
        category: b.category,
        name: b.name,
        description: b.description || '',
        owner: b.owner || '', sla: b.sla || '', steps: [],
        bpmn: versionXmlByKey[b.key] || blankBpmn(traducir, b.name),
        isCustom: true,
        _backendId: b.id,
        _version: b.latest_version || 1,
        _published: b.published_version ?? null,
        _status: b.status,
      }))
    return [...overriddenCatalog, ...customs]
  }, [catalogo, PROCESS_CATALOG, backendProcesses, versionXmlByKey, traducir])

  // Keep selectedProcess fresh when data reloads.
  // Solo queremos reaccionar cuando se recarga la lista del backend
  // (allProcesses cambia de referencia). Añadir selectedProcess a las deps
  // crearía un bucle: el efecto llama a setSelectedProcess, lo que volvería
  // a disparar el efecto inmediatamente.
   
  useEffect(() => {
    if (!selectedProcess) return
    const fresh = allProcesses.find(p => p.id === selectedProcess.id)
    if (fresh && fresh !== selectedProcess) setSelectedProcess(fresh)
    // `selectedProcess` faltaba (auditoría 2026-08, P1-6): si cambiaba la
    // selección sin cambiar la lista, el efecto no se reejecutaba y el proceso
    // seleccionado se quedaba con datos viejos. El guard de desigualdad evita
    // el bucle al escribir el mismo estado que se lee.
  }, [allProcesses, selectedProcess])

  const filtered = allProcesses.filter(p => {
    const catOk = selectedCat === 'all' || p.category === selectedCat
    const q = search.toLowerCase()
    const searchOk = !q || p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q)
    return catOk && searchOk
  })

  // Al cambiar de proceso o entrar a editar se vuelve a la versión vigente.
  useEffect(() => { setVersionAbierta(null) }, [selectedProcess?.id, editMode])

  const currentBpmn = selectedProcess ? (versionAbierta?.xml ?? selectedProcess.bpmn) : null

  const { getXml, errorImport } = useBpmnViewer(containerRef, currentBpmn, editMode)

  /**
   * El registro del proceso en el backend, con `xml` como diagrama vigente.
   * Un proceso del catálogo sin registro se crea; el esqueleto sembrado sin
   * editar recibe una versión nueva con el diagrama que se está viendo.
   */
  async function guardarRegistro(proc: Process, xml: string, nota: string | null): Promise<{ id: string; executable: boolean }> {
    if (!proc._backendId) {
      const created = await bpmnProcessesApi.create({
        name: proc.name,
        key: proc.id,
        category: proc.category || 'admin',
        description: proc.description || '',
        owner: proc.owner || null,
        sla: proc.sla || null,
        bpmn_xml: xml,
      })
      const v = await bpmnProcessesApi.validate(created.data.id)
      return { id: created.data.id, executable: v.data.executable }
    }
    const r = await bpmnProcessesApi.saveVersion(proc._backendId, xml, nota)
    return { id: proc._backendId, executable: r.data.validation.executable }
  }

  async function handleSaveCustom() {
    const xml = await getXml()
    if (!xml || !selectedProcess) return
    setSaving(true)
    try {
      const { executable } = await guardarRegistro(selectedProcess, xml, null)
      setBackend(prev => ({ ...prev, xmlByKey: { ...prev.xmlByKey, [selectedProcess.id]: xml } }))
      await reloadBackend()
      setEditMode(false)
      if (executable) toast.success(traducir('bpm.diseno_guardado'))
      else toast.warning(traducir('bpm.guardado_no_ejecutable'))
    } catch (e) {
      toast.error(apiErrorMsg(e, traducir('bpm.error_guardar')))
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    const xml = await getXml()
    if (!xml) return
    const blob = new Blob([xml], { type: 'application/xml' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `${selectedProcess?.id ?? 'process'}.bpmn`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleAddProcess() {
    if (!newProcess.name.trim()) return
    const key = `custom_${Date.now()}`
    const xml = blankBpmn(traducir, newProcess.name)
      .replace('Process_new', key)
      .replace('Definitions_new', `Def_${key}`)
    setSaving(true)
    try {
      const r = await bpmnProcessesApi.create({
        name: newProcess.name.trim(),
        key,
        category: newProcess.category,
        description: newProcess.description,
        owner: newProcess.owner.trim() || null,
        sla: newProcess.sla.trim() || null,
        bpmn_xml: xml,
      })
      const created = r.data
      setBackend(prev => ({ ...prev, xmlByKey: { ...prev.xmlByKey, [key]: xml } }))
      await reloadBackend()
      const proc = {
        id: key,
        category: newProcess.category,
        name: newProcess.name.trim(),
        description: newProcess.description,
        owner: newProcess.owner, sla: newProcess.sla, steps: [],
        bpmn: xml, isCustom: true,
        _backendId: created.id, _version: 1,
      }
      setNewProcess({ name: '', category: 'proyectos', description: '', owner: '', sla: '' })
      setShowAddForm(false)
      setSelectedProcess(proc)
      setEditMode(true)
      toast.success(traducir('bpm.proceso_creado'))
    } catch (e) {
      toast.error(apiErrorMsg(e, traducir('bpm.error_crear')))
    } finally {
      setSaving(false)
    }
  }

  async function handleStart() {
    if (!selectedProcess) return
    setIniciando(true)
    try {
      let id = selectedProcess._backendId
      if (!id || selectedProcess._esqueleto) {
        // Lo que se ve es lo que se ejecuta (ver cabecera).
        id = (await guardarRegistro(selectedProcess, selectedProcess.bpmn, traducir('bpm.nota_diagrama_catalogo'))).id
        await reloadBackend()
      }
      const v = await bpmnProcessesApi.validate(id)
      if (!v.data.executable) { setProblemas(v.data.problems); return }
      const r = await bpmnProcessesApi.start(id)
      const inst = r.data
      if (inst.status === 'failed') toast.error(textoErrorDeInstancia(traducir, inst) || traducir('bpm.estado_failed'))
      else toast.success(traducir('bpm.instancia_iniciada'))
      setSelectedProcess(null)
      setView('run')
    } catch (e) {
      toast.error(apiErrorMsg(e, traducir('bpm.no_se_pudo_iniciar')))
    } finally {
      setIniciando(false)
    }
  }

  async function handleDelete() {
    if (!selectedProcess?._backendId) return
    if (!await confirmar({ message: traducir('bpm.confirmar_eliminar', { name: selectedProcess.name }), danger: true })) return
    try {
      await bpmnProcessesApi.remove(selectedProcess._backendId)
      toast.success(traducir('bpm.proceso_eliminado'))
      setSelectedProcess(null)
      setEditMode(false)
      await reloadBackend()
    } catch (e) {
      toast.error(apiErrorMsg(e, traducir('bpm.error_eliminar')))
    }
  }

  async function handleArchive() {
    if (!selectedProcess?._backendId) return
    const archivar = selectedProcess._status !== 'archived'
    try {
      await bpmnProcessesApi.update(selectedProcess._backendId, {
        status: archivar ? 'archived' : (selectedProcess._published ? 'published' : 'draft'),
      })
      toast.success(traducir(archivar ? 'bpm.proceso_archivado' : 'bpm.proceso_reactivado'))
      await reloadBackend()
    } catch (e) {
      toast.error(apiErrorMsg(e, traducir('common.error')))
    }
  }

  const catColor = selectedProcess ? CAT_COLOR[selectedProcess.category] : 'var(--accent)'
  const catLabel = (id: string) => {
    const c = CATEGORIES.find(x => x.id === id)
    return c ? traducir(c.labelKey) : id
  }
  const nPasos = selectedProcess?.steps?.length ?? 0

  return (
    <Page
      icon={<Network size={18} />}
      title={traducir('nav.bpm')}
      subtitle={traducir('bpm.subtitle_counts', {
        total: allProcesses.length,
        system: PROCESS_CATALOG.length,
        custom: allProcesses.filter(p => p.isCustom).length,
      })}
      rightActions={
        puedeEditar ? (
          <Button icon={<Plus size={14} />} onClick={() => { setShowAddForm(true); setSelectedProcess(null); setView('catalog') }}>
            {traducir('bpm.nuevo_proceso')}
          </Button>
        ) : undefined
      }
    >
      <Tabs
        items={[
          { id: 'catalog', label: traducir('bpm.catalogo'), icon: <LayoutGrid size={14} /> },
          { id: 'run', label: traducir('bpm.ejecucion'), icon: <Activity size={14} /> },
        ]}
        active={view}
        onChange={id => { if (id === 'run') { setView('run'); setSelectedProcess(null) } else setView('catalog') }}
        ariaLabel={traducir('bpm.vista')}
        className="bpmp-tabs"
      />
      {view === 'run' ? <BpmRunPanel /> : (
      <div className="bpmp-layout">

        {/* ── SIDEBAR ─────────────────────────────────────────────── */}
        <nav className="ds-card bpmp-sidebar" aria-label={traducir('bpm.categoria')}>
          <div className="bpmp-search">
            <Search size={13} aria-hidden className="bpmp-search__icon" />
            <input aria-label={traducir('bpm.buscar_proceso')}
              type="search"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={traducir('bpm.buscar_proceso')}
              className="ds-input"
            />
          </div>
          <div className="bpmp-cats">
            {CATEGORIES.map(cat => {
              const count = cat.id === 'all' ? allProcesses.length : allProcesses.filter(p => p.category === cat.id).length
              const active = selectedCat === cat.id
              return (
                <Pulsable
                  type="button"
                  key={cat.id}
                  aria-pressed={active}
                  onClick={() => { setSelectedCat(cat.id); setSelectedProcess(null); setEditMode(false) }}
                  className="bpmp-cat"
                  style={catVar('--bpmp-cat', cat.color)}
                >
                  <span>{traducir(cat.labelKey)}</span>
                  <span className="bpmp-cat__count">{count}</span>
                </Pulsable>
              )
            })}
          </div>
        </nav>

        {/* ── MAIN AREA ────────────────────────────────────────────── */}
        <div className="bpmp-main">
          {errorCarga && <div role="alert" className="bprupa-box-2">{traducir('bpm.error_cargar')}</div>}

          {/* ── ADD FORM ── */}
          {showAddForm && (
            <div className="bpmp-card bpmp-card--form">
              <div className="bpmp-form-head">
                <div className="u-md-700">{traducir('bpm.nuevo_proceso_personalizado')}</div>
                <IconButton onClick={() => setShowAddForm(false)} ariaLabel={traducir('bpm.cerrar_formulario')}>
                  <X size={16} aria-hidden />
                </IconButton>
              </div>
              <div className="bpmp-form-grid">
                <div>
                  <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="bpmp-label">{traducir('bpm.nombre_del_proceso')}</label>
                  <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={newProcess.name} onChange={e => setNewProcess(p => ({ ...p, name: e.target.value }))} placeholder={traducir('bpm.ej_gestion_de_proveedores')} className="bpmp-input" />
                </div>
                <div>
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="bpmp-label">{traducir('bpm.categoria')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-2`} value={newProcess.category} onChange={e => setNewProcess(p => ({ ...p, category: e.target.value }))} className="bpmp-input">
                    {CATEGORIES.filter(c => c.id !== 'all').map(c => <option key={c.id} value={c.id}>{traducir(c.labelKey)}</option>)}
                  </Select>
                </div>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="bpmp-label">{traducir('bpm.responsable')}</label>
                  <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={newProcess.owner} onChange={e => setNewProcess(p => ({ ...p, owner: e.target.value }))} placeholder={traducir('bpm.ej_pm')} className="bpmp-input" />
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="bpmp-label">{traducir('bpm.sla')}</label>
                  <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={newProcess.sla} onChange={e => setNewProcess(p => ({ ...p, sla: e.target.value }))} placeholder={traducir('bpm.ej_3_dias')} className="bpmp-input" />
                </div>
              </div>
              <div className="u-mb-12">
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="bpmp-label">{traducir('bpm.descripcion')}</label>
                <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={newProcess.description} onChange={e => setNewProcess(p => ({ ...p, description: e.target.value }))} placeholder={traducir('bpm.describe_brevemente_el_proceso')} className="bpmp-input" />
              </div>
              <div className="u-row-8">
                <Button disabled={!newProcess.name.trim()} onClick={handleAddProcess}>{traducir('bpm.crear_y_disenar')}</Button>
                <Button variant="secondary" onClick={() => setShowAddForm(false)}>{traducir('common.cancel')}</Button>
              </div>
            </div>
          )}

          {selectedProcess ? (
            /* ── PROCESS DETAIL VIEW ── */
            <div className="bpmp-detail" style={catVar('--bpmp-tag', catColor)}>
              {/* Header */}
              <div className="bpmp-detail__head">
                <Button variant="ghost" size="sm" icon={<ChevronLeft size={14} />} onClick={() => { setSelectedProcess(null); setEditMode(false) }}>
                  {traducir('bpm.volver')}
                </Button>
                <div className="bpmp-tag">{catLabel(selectedProcess.category)}</div>
                <div className="bpmp-detail__title">{selectedProcess.name}</div>
                {selectedProcess.isCustom && <div className="bpmp-tag bpmp-tag--custom">{traducir('bpm.personalizado')}</div>}
                {selectedProcess._status === 'archived' && <div className="bpmp-tag">{traducir('bpm.archivado')}</div>}
                {selectedProcess._backendId && (
                  <div className="bpmp-tag">
                    {selectedProcess._published ? traducir('bpm.publicada_vn', { n: selectedProcess._published }) : traducir('bpm.borrador_vn', { n: selectedProcess._version ?? 1 })}
                  </div>
                )}
                <div className="u-flex1" />
                <Button variant="ghost" size="sm" icon={<Download size={14} />} onClick={handleExport}>
                  {traducir('bpm.exportar_bpmn')}
                </Button>
                {!editMode && selectedProcess._backendId && (
                  <Button variant="ghost" size="sm" icon={<History size={14} />} onClick={() => setVerVersiones(true)}>
                    {traducir('bpm.versiones')}
                  </Button>
                )}
                {!editMode && puedeEditar && selectedProcess._backendId && (
                  <Button variant="ghost" size="sm" icon={<Archive size={14} />} onClick={handleArchive}>
                    {traducir(selectedProcess._status === 'archived' ? 'bpm.reactivar' : 'bpm.archivar')}
                  </Button>
                )}
                {!editMode && puedeEditar && selectedProcess.isCustom && selectedProcess._backendId && (
                  <Button variant="danger" size="sm" icon={<Trash2 size={14} />} onClick={handleDelete}>
                    {traducir('common.delete')}
                  </Button>
                )}
                {puedeEditar && (editMode ? (
                  <Button icon={<Save size={14} />} onClick={handleSaveCustom} disabled={saving} loading={saving}>
                    {saving ? traducir('common.saving') : traducir('bpm.guardar_diseno')}
                  </Button>
                ) : (
                  <Button variant="secondary" icon={<Edit3 size={14} />} onClick={() => setEditMode(true)}>
                    {traducir('bpm.editar')}
                  </Button>
                ))}
                {!editMode && puedeEditar && selectedProcess._status !== 'archived' && !versionAbierta && (
                  <Button icon={<Play size={14} />} onClick={handleStart} loading={iniciando} disabled={iniciando}>{traducir('bpm.iniciar')}</Button>
                )}
              </div>

              {/* Meta info */}
              <div className="bpmp-meta">
                {selectedProcess.owner && (
                  <div className="bpmp-meta__item">
                    <User size={12} aria-hidden="true" /><strong>{traducir('bpm.responsable_dp')}</strong> {selectedProcess.owner}
                  </div>
                )}
                {selectedProcess.sla && (
                  <div className="bpmp-meta__item">
                    <Timer size={12} aria-hidden="true" /><strong>{traducir('bpm.sla_dp')}</strong> {selectedProcess.sla}
                  </div>
                )}
                {selectedProcess.description && (
                  <div className="bpmp-meta__item">
                    {selectedProcess.description}
                  </div>
                )}
              </div>

              {/* Steps summary */}
              {nPasos > 0 && (
                <ol className="bpmp-steps" aria-label={traducir('bpm.pasos_del_proceso')}>
                  {(selectedProcess.steps || []).map((step, i) => (
                    <li key={i} className="bpmp-step">
                      <div className="bpmp-step__box">
                        <span className="bpmp-step__num">{i + 1}.</span>
                        {step}
                      </div>
                      {i < nPasos - 1 && (
                        <div className="bpmp-step__sep" aria-hidden="true"><ChevronRight size={12} /></div>
                      )}
                    </li>
                  ))}
                </ol>
              )}

              {/* BPMN Diagram */}
              <div className="bpmp-diagram-wrap">
                {editMode && (
                  <div className="bpmp-edit-badge" role="status">
                    <Edit3 size={11} aria-hidden /> {traducir('bpm.modo_edicion_arrastra_nodos_anade_elementos_desde')}
                  </div>
                )}
                {versionAbierta && !editMode && (
                  <div className="bpmp-edit-badge" role="status">
                    {traducir('bpm.viendo_version', { n: versionAbierta.version })}{' '}
                    <Button variant="ghost" size="xs" onClick={() => setVersionAbierta(null)}>{traducir('bpm.volver_a_la_vigente')}</Button>
                  </div>
                )}
                {errorImport && <div role="alert" className="bprupa-box-2">{traducir('bpm.error_diagrama')}</div>}
                <div ref={containerRef} className="bpmp-diagram" />
              </div>
            </div>
          ) : (
            /* ── CATALOG GRID ── */
            <div className="bpmp-catalog">
              {filtered.length === 0 ? (
                <div className="ds-card">
                  <EmptyState
                    icon={search ? <SearchX size={28} /> : <Workflow size={28} />}
                    title={search ? traducir('bpm.sin_resultados_para', { q: search }) : traducir('bpm.sin_procesos_categoria')}
                    description={search ? traducir('bpm.prueba_otro_termino') : traducir('bpm.crea_el_primero')}
                    action={!search && puedeEditar
                      ? <Button icon={<Plus size={14} />} onClick={() => setShowAddForm(true)}>{traducir('bpm.nuevo_proceso')}</Button>
                      : undefined}
                  />
                </div>
              ) : (
                <div className="bpmp-grid">
                  {filtered.map(proc => {
                    const color = CAT_COLOR[proc.category] || 'var(--accent)'
                    return (
                      <Pulsable
                        type="button"
                        key={proc.id}
                        className="bpmp-card bpmp-proc"
                        style={catVar('--bpmp-tag', color)}
                        onClick={() => { setSelectedProcess(proc); setEditMode(false); setShowAddForm(false) }}
                      >
                        <div className="bpmp-proc__head">
                          <div className="bpmp-proc__name">{proc.name}</div>
                          {proc.isCustom && <div className="bpmp-tag bpmp-tag--custom bpmp-tag--aside">{traducir('bpm.custom')}</div>}
                        </div>
                        <div className="bpmp-proc__cat">
                          <span className="bpmp-tag">{catLabel(proc.category)}</span>
                        </div>
                        {proc.description && (
                          <div className="bpmp-proc__desc">
                            {proc.description.length > 90 ? proc.description.slice(0, 88) + '…' : proc.description}
                          </div>
                        )}
                        <div className="bpmp-proc__facts">
                          {proc.owner && <span className="bpmp-fact"><User size={12} aria-hidden="true" />{proc.owner}</span>}
                          {proc.sla   && <span className="bpmp-fact"><Timer size={12} aria-hidden="true" />{proc.sla}</span>}
                          {(proc.steps?.length ?? 0) > 0 && <span className="bpmp-fact"><ListOrdered size={12} aria-hidden="true" />{traducir('bpm.n_pasos', { n: proc.steps?.length ?? 0 })}</span>}
                        </div>
                        <div className="bpmp-proc__cta">
                          {traducir('bpm.ver_diagrama')} <ChevronRight size={12} aria-hidden="true" />
                        </div>
                      </Pulsable>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      )}
      {verVersiones && selectedProcess?._backendId && (
        <BpmVersionsModal
          processId={selectedProcess._backendId}
          puedePublicar={puedeEditar}
          onAbrir={(version, xml) => { setEditMode(false); setVersionAbierta({ version, xml }); setVerVersiones(false) }}
          onPublicada={() => { reloadBackend() }}
          onClose={() => setVerVersiones(false)}
        />
      )}
      {problemas && <BpmProblemsModal problemas={problemas} onClose={() => setProblemas(null)} />}
    </Page>
  )
}
