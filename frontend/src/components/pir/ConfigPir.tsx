/**
 * Sección «Revisión posterior a la implantación (PIR)» de Configuración (`/settings/pir`,
 * capacidad `pir.administrar`; migración 206, docs/PIR.md).
 *
 * - Plazos y avisos: días hasta la PIR de un cambio y de un proyecto, aviso previo.
 * - Cuándo se programa: cambio al implantarse o al cerrarse; proyecto en la puesta en
 *   marcha, en el cierre o en ambos.
 * - Obligatoriedad: por tipo de cambio (normal, emergencia, estándar) y de proyecto
 *   (por defecto; cada plantilla puede decir otra cosa para su tipo).
 * - Segregación: quien implantó o gestionó no aprueba su PIR.
 * - Proyecto de mejora continua: donde nacen las tareas de las acciones de PIR de
 *   cambios sin proyecto.
 * - Plantillas: preguntas y criterios por ámbito y tipo (vacío = cualquiera), con su
 *   plazo y obligatoriedad; «Cargar las de fábrica» trae ITIL 4 / PMBOK en tu idioma.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, ListChecks, Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-react'
import { Button, Card, IconButton, Input, Modal, Segmentado, SelectRico, Spinner, StatusBadge, Switch, Tabla } from '../ui'
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { useListaDeProyectos } from '../../hooks/useListas'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type { ConfigPir as Config, ItemDePlantilla, OrigenPir, PlantillaPir, PlantillaPirIn } from '../../services/api/pir'
import './Pir.css'

const TIPOS_DE_CAMBIO = ['normal', 'emergency', 'standard']

export default function ConfigPir() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: config, isLoading } = useQuery({ queryKey: CLAVES_PIR.config, queryFn: () => pirApi.config() })
  const { data: proyectos = [] } = useListaDeProyectos()
  const [form, setForm] = useState<Config | null>(null)
  useEffect(() => { if (config) setForm(config) }, [config])
  const guardar = useMutation({
    mutationFn: (c: Partial<Config>) => pirApi.guardarConfig(c),
    onSuccess: c => { qc.setQueryData(CLAVES_PIR.config, c); toast.success(t('pir.guardado')) },
    onError: e => toast.error(extractErr(e)),
  })
  if (isLoading || !form) return <Spinner />
  const set = <K extends keyof Config>(k: K, v: Config[K]) => setForm(f => (f ? { ...f, [k]: v } : f))
  const entero = (v: string) => Math.max(0, Math.min(365, Number(v) || 0))

  return (
    <div className="u-stack-16">
      <Card>
        <h3 className="pir-bloque__titulo"><Clock size={16} aria-hidden />{t('pir.cfg_plazos')}</h3>
        <div className="pir-rejilla">
          <Input label={t('pir.cfg_dias_cambio')} type="number" min={0} max={365} value={form.dias_cambio}
            onChange={e => set('dias_cambio', entero(e.target.value))} />
          <Input label={t('pir.cfg_dias_proyecto')} type="number" min={0} max={365} value={form.dias_proyecto}
            onChange={e => set('dias_proyecto', entero(e.target.value))} />
          <Input label={t('pir.cfg_aviso')} type="number" min={0} max={365} value={form.aviso_dias_antes}
            onChange={e => set('aviso_dias_antes', entero(e.target.value))} />
        </div>
        <div className="pir-rejilla">
          <div className="u-stack-6"><span className="pir-apagado">{t('pir.cfg_momento_cambio')}</span>
            <Segmentado aria-label={t('pir.cfg_momento_cambio')} valor={form.momento_cambio} onChange={v => set('momento_cambio', v as Config['momento_cambio'])}
              opciones={[{ valor: 'implantacion', etiqueta: t('pir.motivo_implantacion') }, { valor: 'cierre', etiqueta: t('pir.motivo_cierre') }]} /></div>
          <div className="u-stack-6"><span className="pir-apagado">{t('pir.cfg_momento_proyecto')}</span>
            <Segmentado aria-label={t('pir.cfg_momento_proyecto')} valor={form.momento_proyecto} onChange={v => set('momento_proyecto', v as Config['momento_proyecto'])}
              opciones={[{ valor: 'go_live', etiqueta: t('pir.motivo_go_live') }, { valor: 'cierre', etiqueta: t('pir.motivo_cierre') },
                { valor: 'ambos', etiqueta: t('pir.cfg_ambos') }]} /></div>
        </div>
      </Card>
      <Card>
        <h3 className="pir-bloque__titulo"><ShieldCheck size={16} aria-hidden />{t('pir.cfg_obligatoriedad')}</h3>
        <div className="u-stack-8">
          <Switch checked={form.obligatorio_normal} onChange={v => set('obligatorio_normal', v)} label={t('pir.cfg_obl_normal')} />
          <Switch checked={form.obligatorio_emergencia} onChange={v => set('obligatorio_emergencia', v)} label={t('pir.cfg_obl_emergencia')} />
          <Switch checked={form.obligatorio_estandar} onChange={v => set('obligatorio_estandar', v)} label={t('pir.cfg_obl_estandar')}
            ayuda={t('pir.cfg_obl_estandar_ayuda')} />
          <Switch checked={form.obligatorio_proyecto} onChange={v => set('obligatorio_proyecto', v)} label={t('pir.cfg_obl_proyecto')}
            ayuda={t('pir.cfg_obl_proyecto_ayuda')} />
          <Switch checked={form.segregacion} onChange={v => set('segregacion', v)} label={t('pir.cfg_segregacion')}
            ayuda={t('pir.cfg_segregacion_ayuda')} />
          <SelectRico label={t('pir.cfg_proyecto_acciones')} hint={t('pir.cfg_proyecto_acciones_ayuda')}
            valor={form.proyecto_acciones_id ?? ''} onChange={v => set('proyecto_acciones_id', v || null)}
            opciones={[{ valor: '', etiqueta: t('pir.cfg_sin_proyecto') }, ...proyectos.map(p => ({ valor: p.id, etiqueta: `${p.code} · ${p.name}` }))]} />
        </div>
        <div className="pir-acciones-pie">
          <Button onClick={() => guardar.mutate(form)} loading={guardar.isPending}>{t('pir.guardar')}</Button>
        </div>
      </Card>
      <Plantillas />
    </div>
  )
}

function Plantillas() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: CLAVES_PIR.plantillas, queryFn: () => pirApi.plantillas() })
  const [editando, setEditando] = useState<PlantillaPir | 'nueva' | null>(null)
  const borrar = useMutation({
    mutationFn: (id: string) => pirApi.borrarPlantilla(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: CLAVES_PIR.plantillas }); toast.success(t('pir.guardado')) },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Card>
      <div className="u-row-center-8">
        <h3 className="pir-bloque__titulo"><ListChecks size={16} aria-hidden />{t('pir.cfg_plantillas')}</h3>
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('pir.cfg_nueva_plantilla')}</Button>
      </div>
      <p className="pir-apagado">{t('pir.cfg_plantillas_ayuda')}</p>
      <Tabla<PlantillaPir>
        etiqueta={t('pir.cfg_plantillas')}
        filas={data}
        cargando={isLoading}
        vacio={{ icono: <ListChecks size={28} />, titulo: t('pir.cfg_sin_plantillas'), descripcion: t('pir.cfg_sin_plantillas_desc') }}
        columnas={[
          { key: 'nombre', label: t('pir.cfg_nombre'), cabeceraDeFila: true },
          { key: 'ambito', label: t('pir.ambito'), render: (_v, p) => t(`pir.origen_${p.ambito}`) },
          { key: 'tipo', label: t('pir.tipo'), render: (_v, p) => p.tipo ?? t('pir.cualquiera') },
          { key: 'obligatorio', label: t('pir.obligatoria'), render: (_v, p) => (p.obligatorio === null ? t('pir.segun_config') : p.obligatorio ? t('pir.si') : t('pir.no')) },
          { key: 'dias', label: t('pir.cfg_dias'), render: (_v, p) => p.dias ?? t('pir.segun_config') },
          { key: 'criterios', label: t('pir.criterios'), render: (_v, p) => `${p.criterios.length} / ${p.preguntas.length}` },
          { key: 'activo', label: t('pir.cfg_activa'), render: (_v, p) => <StatusBadge kind={p.activo ? 'success' : 'neutral'}>{p.activo ? t('pir.si') : t('pir.no')}</StatusBadge> },
          { key: 'acciones', label: <span className="u-sr-only">{t('pir.acciones')}</span>, sortable: false, render: (_v, p) => (
            <div className="ui-acciones">
              <IconButton variante="caja" ariaLabel={t('pir.cfg_editar', { nombre: p.nombre })} onClick={() => setEditando(p)}><Pencil /></IconButton>
              <IconButton variante="caja" tono="peligro" ariaLabel={t('pir.cfg_borrar', { nombre: p.nombre })}
                onClick={async () => { if (await confirmar({ message: t('pir.cfg_borrar_confirmar', { nombre: p.nombre }), danger: true })) borrar.mutate(p.id) }}><Trash2 /></IconButton>
            </div>) },
        ]}
      />
      {editando && <EditorDePlantilla plantilla={editando === 'nueva' ? null : editando} onClose={() => setEditando(null)} />}
    </Card>
  )
}

function EditorDePlantilla({ plantilla, onClose }: { plantilla: PlantillaPir | null; onClose: () => void }) {
  const t = useAppT()
  const { lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState<PlantillaPirIn>(() => plantilla ? { ...plantilla } : {
    nombre: '', ambito: 'change', tipo: null, obligatorio: null, dias: null, criterios: [], preguntas: [], activo: true,
  })
  const [cambiado, setCambiado] = useState(false)
  const set = <K extends keyof PlantillaPirIn>(k: K, v: PlantillaPirIn[K]) => { setF(x => ({ ...x, [k]: v })); setCambiado(true) }
  const guardar = useMutation({
    mutationFn: () => (plantilla ? pirApi.editarPlantilla(plantilla.id, f) : pirApi.crearPlantilla(f)),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: CLAVES_PIR.plantillas }); toast.success(t('pir.guardado')); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  const fabrica = useMutation({
    mutationFn: () => pirApi.deFabrica((f.ambito ?? 'change') as OrigenPir, lang),
    onSuccess: r => { set('criterios', r.criterios); set('preguntas', r.preguntas) },
    onError: e => toast.error(extractErr(e)),
  })
  const listas = (k: 'criterios' | 'preguntas', titulo: string) => {
    const items: ItemDePlantilla[] = f[k] ?? []
    return (
      <div className="u-stack-8">
        <span className="pir-bloque__titulo">{titulo}</span>
        {items.map((it, i) => (
          <div key={i} className="pir-fila-editable">
            <Input aria-label={titulo} value={it.texto} onChange={e => set(k, items.map((x, j) => (j === i ? { ...x, texto: e.target.value } : x)))} />
            <IconButton variante="caja" tono="peligro" ariaLabel={t('pir.cfg_quitar', { texto: it.texto })}
              onClick={() => set(k, items.filter((_x, j) => j !== i))}><X /></IconButton>
          </div>
        ))}
        <div><Button size="sm" variant="ghost" icon={<Plus size={12} />} onClick={() => set(k, [...items, { clave: '', texto: '' }])}>{t('pir.cfg_anadir')}</Button></div>
      </div>
    )
  }
  return (
    <Modal open title={plantilla ? t('pir.cfg_editar', { nombre: plantilla.nombre }) : t('pir.cfg_nueva_plantilla')} onClose={onClose} size="lg"
      cambiosSinGuardar={cambiado}>
      <div className="u-stack-12">
        <div className="pir-rejilla">
          <Input label={t('pir.cfg_nombre')} value={f.nombre ?? ''} onChange={e => set('nombre', e.target.value)} />
          <div className="u-stack-6"><span className="pir-apagado">{t('pir.ambito')}</span>
            <Segmentado aria-label={t('pir.ambito')} valor={f.ambito ?? 'change'} onChange={v => { set('ambito', v as OrigenPir); set('tipo', null) }}
              opciones={[{ valor: 'change', etiqueta: t('pir.origen_change') }, { valor: 'project', etiqueta: t('pir.origen_project') }]} /></div>
          {f.ambito === 'change' ? (
            <SelectRico label={t('pir.tipo')} valor={f.tipo ?? ''} onChange={v => set('tipo', v || null)}
              opciones={[{ valor: '', etiqueta: t('pir.cualquiera') }, ...TIPOS_DE_CAMBIO.map(x => ({ valor: x, etiqueta: t(`pir.tipo_cambio_${x}`) }))]} />
          ) : (
            <Input label={t('pir.cfg_tipo_proyecto')} hint={t('pir.cfg_tipo_proyecto_ayuda')} value={f.tipo ?? ''} onChange={e => set('tipo', e.target.value || null)} />
          )}
          <SelectRico label={t('pir.obligatoria')} valor={f.obligatorio === null || f.obligatorio === undefined ? '' : f.obligatorio ? 'si' : 'no'}
            onChange={v => set('obligatorio', v === '' ? null : v === 'si')}
            opciones={[{ valor: '', etiqueta: t('pir.segun_config') }, { valor: 'si', etiqueta: t('pir.si') }, { valor: 'no', etiqueta: t('pir.no') }]} />
          <Input label={t('pir.cfg_dias')} hint={t('pir.cfg_dias_ayuda')} type="number" min={0} max={365} value={f.dias ?? ''}
            onChange={e => set('dias', e.target.value === '' ? null : Math.max(0, Math.min(365, Number(e.target.value) || 0)))} />
        </div>
        <Switch checked={f.activo ?? true} onChange={v => set('activo', v)} label={t('pir.cfg_activa')} />
        <div><Button size="sm" variant="secondary" loading={fabrica.isPending} onClick={() => fabrica.mutate()}>{t('pir.cfg_cargar_fabrica')}</Button></div>
        {listas('criterios', t('pir.criterios'))}
        {listas('preguntas', t('pir.preguntas'))}
        <div className="pir-acciones-pie">
          <Button variant="secondary" onClick={onClose}>{t('pir.cancelar')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.nombre?.trim()}>{t('pir.guardar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
