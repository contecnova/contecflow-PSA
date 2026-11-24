/**
 * Configuración › Personas › Mi cuaderno (`/settings/cuaderno`, capacidad
 * `cuaderno.config`; docs/CUADERNO.md §Configuración).
 *
 * - Etiquetas por defecto de la empresa (cada persona puede crear las suyas).
 * - Qué pasa con los cuadernos de quien se da de baja (a su responsable, a la
 *   papelera o se conservan), días de papelera, IA y voz, y con quién se puede compartir.
 * - Plantillas de página (acta de reunión, seguimiento de cliente, 1:1, lluvia de ideas…).
 * - Acceso excepcional (capacidad `cuaderno.acceso_excepcional`): solo con un
 *   bloqueo legal activo o una solicitud RGPD en curso de esa persona; auditado.
 * Guardar queda auditado en el servidor (antes y después).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { TaskItem, TaskList } from '@tiptap/extension-list'
import { TableKit } from '@tiptap/extension-table'
import { FileText, Lock, Plus, ShieldAlert, Tag, Trash2, UserMinus } from 'lucide-react'
import {
  Button, FormField, IconButton, Input, Modal, Section, Select, Spinner, Switch, Textarea, UserSelect,
} from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { confirmar } from '../../context/ConfirmContext'
import { downloadBlob, extractErr } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'
import type { ConfigCuaderno as Config, DocJSON, Plantilla } from '../../services/api/cuaderno'
import { COLORES, ICONOS_DE_ETIQUETA, IconoDeEtiqueta } from './comun'
import './cuaderno.css'

function EditorDePlantilla({ inicial, onCambio }: { inicial?: DocJSON; onCambio: (d: DocJSON) => void }) {
  const t = useAppT()
  const editor = useEditor({
    extensions: [StarterKit, TaskList, TaskItem.configure({ nested: true }), TableKit],
    content: inicial || { type: 'doc', content: [{ type: 'paragraph' }] },
    editorProps: { attributes: { class: 'cdn-editor__texto', 'aria-label': t('cuaderno.plantilla_contenido') } },
    onUpdate: ({ editor: e }) => onCambio(e.getJSON() as DocJSON),
  })
  return <EditorContent editor={editor} className="cdn-editor__cuerpo cdn-editor__cuerpo--plantilla" />
}

function ModalPlantilla({ plantilla, onClose }: { plantilla: Plantilla | null; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const nueva = !plantilla
  const [clave, setClave] = useState(plantilla?.key || '')
  const [nombre, setNombre] = useState(plantilla?.name || '')
  const [descripcion, setDescripcion] = useState(plantilla?.description || '')
  const [activa, setActiva] = useState(plantilla?.is_active ?? true)
  const [contenido, setContenido] = useState<DocJSON | undefined>(plantilla?.content)
  const guardar = useMutation({
    mutationFn: () => cuadernoApi.guardarPlantilla({ key: clave, name: nombre, description: descripcion || null, content: contenido,
      is_active: activa, sort_order: plantilla?.sort_order ?? 50 }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cuaderno', 'config', 'plantillas'] }); void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.plantillas }); toast.success(t('cuaderno.plantilla_guardada')); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open onClose={onClose} title={nueva ? t('cuaderno.nueva_plantilla') : t('cuaderno.editar_plantilla')} size="xl">
      <div className="cdn-form">
        <div className="cdn-form__fila">
          <Input label={t('cuaderno.plantilla_clave')} value={clave} onChange={e => setClave(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
            disabled={!nueva} maxLength={60} hint={t('cuaderno.plantilla_clave_ayuda')} required />
          <Input label={t('cuaderno.plantilla_nombre')} value={nombre} onChange={e => setNombre(e.target.value)} maxLength={200} required />
        </div>
        <Input label={t('cuaderno.plantilla_descripcion')} value={descripcion} onChange={e => setDescripcion(e.target.value)} maxLength={500} />
        <Switch checked={activa} onChange={setActiva} label={t('cuaderno.plantilla_activa')} />
        <FormField label={t('cuaderno.plantilla_contenido')}>
          <div><EditorDePlantilla inicial={plantilla?.content} onCambio={setContenido} /></div>
        </FormField>
        <div className="cdn-form__acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} disabled={!/^[a-z][a-z0-9_]{0,59}$/.test(clave) || !nombre.trim()} loading={guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function AccesoExcepcional() {
  const t = useAppT()
  const toast = useToast()
  const [persona, setPersona] = useState('')
  const [bloqueo, setBloqueo] = useState('')
  const [rgpd, setRgpd] = useState('')
  const [justificacion, setJustificacion] = useState('')
  const [formato, setFormato] = useState<'md' | 'pdf'>('md')
  const pedir = useMutation({
    mutationFn: () => cuadernoApi.accesoExcepcional(persona, { legal_hold_id: bloqueo || undefined, gdpr_request_id: rgpd || undefined, justification: justificacion, format: formato }),
    onSuccess: b => { downloadBlob(b, `cuadernos.${formato}`); toast.success(t('cuaderno.excepcional_hecho')) },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <div className="cdn-form">
      <p className="cdn-ayuda">{t('cuaderno.excepcional_ayuda')}</p>
      <div className="cdn-form__fila">
        <FormField label={t('cuaderno.excepcional_persona')}><UserSelect value={persona} onChange={id => setPersona(id)} /></FormField>
        <Input label={t('cuaderno.excepcional_bloqueo')} value={bloqueo} onChange={e => setBloqueo(e.target.value.trim())} maxLength={36} />
        <Input label={t('cuaderno.excepcional_rgpd')} value={rgpd} onChange={e => setRgpd(e.target.value.trim())} maxLength={36} />
      </div>
      <Textarea label={t('cuaderno.excepcional_justificacion')} value={justificacion} onChange={e => setJustificacion(e.target.value)} rows={3} maxLength={2000} required />
      <div className="cdn-form__acciones">
        <Select suelto tamano="sm" value={formato} onChange={e => setFormato(e.target.value as 'md' | 'pdf')} placeholder={false} aria-label={t('cuaderno.formato')}
          options={[{ value: 'md', label: 'Markdown' }, { value: 'pdf', label: 'PDF' }]} />
        <Button variant="danger" icon={<Lock size={14} />} disabled={!persona || (!bloqueo && !rgpd) || justificacion.trim().length < 10} loading={pedir.isPending}
          onClick={async () => { if (await confirmar({ message: t('cuaderno.excepcional_confirmar'), danger: true })) pedir.mutate() }}>
          {t('cuaderno.excepcional_pedir')}
        </Button>
      </div>
    </div>
  )
}

export default function ConfigCuaderno() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const { data: config, isLoading } = useQuery({ queryKey: CLAVES_CUADERNO.config, queryFn: cuadernoApi.config })
  const { data: plantillas = [] } = useQuery({ queryKey: ['cuaderno', 'config', 'plantillas'], queryFn: cuadernoApi.todasLasPlantillas })
  const [b, setB] = useState<Config | null>(null)
  const [editando, setEditando] = useState<Plantilla | null | 'nueva'>(null)
  useEffect(() => { if (config && !b) setB(structuredClone(config)) }, [config, b])
  const guardar = useMutation({
    mutationFn: (c: Config) => cuadernoApi.guardarConfig(c),
    onSuccess: n => { setB(structuredClone(n)); qc.setQueryData(CLAVES_CUADERNO.config, n); void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol }); toast.success(t('cuaderno.config_guardada')) },
    onError: e => toast.error(extractErr(e)),
  })
  const borrarPlantilla = useMutation({
    mutationFn: (k: string) => cuadernoApi.borrarPlantilla(k),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cuaderno', 'config', 'plantillas'] }); void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.plantillas }) },
    onError: e => toast.error(extractErr(e)),
  })
  if (isLoading || !b) return <Spinner />
  const tag = (i: number, c: Partial<Config['tags'][number]>) => setB(x => (x ? { ...x, tags: x.tags.map((e, j) => (j === i ? { ...e, ...c } : e)) } : x))

  return (
    <div className="cdn-config">
      <Section title={<span className="cdn-seccion"><UserMinus size={15} />{t('cuaderno.config_general')}</span>} subtitle={t('cuaderno.config_general_d')}>
        <div className="cdn-form">
          <div className="cdn-form__fila">
            <Select label={t('cuaderno.config_baja')} value={b.offboarding} placeholder={false}
              onChange={e => setB({ ...b, offboarding: e.target.value as Config['offboarding'] })}
              options={(['transfer', 'trash', 'keep'] as const).map(v => ({ value: v, label: t(`cuaderno.baja_${v}`) }))} hint={t('cuaderno.config_baja_ayuda')} />
            <Input label={t('cuaderno.config_papelera')} type="number" min={1} max={3650} value={String(b.trash_days)}
              onChange={e => setB({ ...b, trash_days: Number(e.target.value) || 30 })} hint={t('cuaderno.config_papelera_ayuda')} />
          </div>
          <Switch checked={b.ai_enabled} onChange={v => setB({ ...b, ai_enabled: v })} label={t('cuaderno.config_ia')} ayuda={t('cuaderno.config_ia_ayuda')} />
          <Switch checked={b.voice_enabled} onChange={v => setB({ ...b, voice_enabled: v })} label={t('cuaderno.config_voz')} ayuda={t('cuaderno.config_voz_ayuda')} />
          <h3 className="ds-eyebrow">{t('cuaderno.config_compartir')}</h3>
          {(['users', 'teams', 'departments'] as const).map(k => (
            <Switch key={k} checked={b.sharing[k]} onChange={v => setB({ ...b, sharing: { ...b.sharing, [k]: v } })} label={t(`cuaderno.config_compartir_${k}`)} />
          ))}
        </div>
      </Section>

      <Section title={<span className="cdn-seccion"><Tag size={15} />{t('cuaderno.config_etiquetas')}</span>} subtitle={t('cuaderno.config_etiquetas_d')}
        actions={<Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setB({ ...b, tags: [...b.tags, { key: `tag_${b.tags.length + 1}`, label: '', color: 'gray', icon: 'bookmark' }] })}>{t('cuaderno.anadir_etiqueta')}</Button>}>
        <ul className="cdn-lista">
          {b.tags.map((e, i) => (
            <li key={i} className="cdn-lista__fila cdn-config__etiqueta">
              <span className={`cdn-etiqueta cdn-color--${e.color}`}><IconoDeEtiqueta icono={e.icon} /></span>
              <Input aria-label={t('cuaderno.etiqueta_clave')} value={e.key} maxLength={40} onChange={ev => tag(i, { key: ev.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })} />
              <Input aria-label={t('cuaderno.etiqueta_nombre')} value={e.label} maxLength={80} onChange={ev => tag(i, { label: ev.target.value })} placeholder={t('cuaderno.etiqueta_nombre')} />
              <Select suelto tamano="sm" value={e.color} placeholder={false} aria-label={t('cuaderno.etiqueta_color')} onChange={ev => tag(i, { color: ev.target.value })}
                options={COLORES.map(c => ({ value: c, label: t(`cuaderno.color_${c}`) }))} />
              <Select suelto tamano="sm" value={e.icon} placeholder={false} aria-label={t('cuaderno.etiqueta_icono')} onChange={ev => tag(i, { icon: ev.target.value })}
                options={ICONOS_DE_ETIQUETA.map(c => ({ value: c, label: t(`cuaderno.icono_${c.replace(/-/g, '_')}`) }))} />
              <IconButton ariaLabel={t('cuaderno.quitar_etiqueta')} className="cdn-boton" onClick={() => setB({ ...b, tags: b.tags.filter((_, j) => j !== i) })}><Trash2 size={14} /></IconButton>
            </li>
          ))}
        </ul>
      </Section>
      <div className="cdn-form__acciones">
        <Button onClick={() => guardar.mutate(b)} loading={guardar.isPending}>{t('common.save')}</Button>
      </div>

      <Section title={<span className="cdn-seccion"><FileText size={15} />{t('cuaderno.config_plantillas')}</span>} subtitle={t('cuaderno.config_plantillas_d')}
        actions={<Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('cuaderno.nueva_plantilla')}</Button>}>
        <ul className="cdn-lista">
          {plantillas.map(p => (
            <li key={p.key} className="cdn-lista__fila">
              <span className="cdn-lista__texto"><strong>{p.name}</strong>
                <span className="cdn-lista__sub">{p.key}{p.builtin ? ` · ${t('cuaderno.de_fabrica')}` : ''}{p.is_active ? '' : ` · ${t('cuaderno.inactiva')}`}</span></span>
              <Button size="sm" variant="ghost" onClick={() => setEditando(p)}>{t('cuaderno.editar')}</Button>
              {p.custom && (
                <IconButton ariaLabel={p.builtin ? t('cuaderno.restablecer_plantilla') : t('cuaderno.borrar_plantilla')} className="cdn-boton"
                  onClick={async () => { if (await confirmar({ message: t('cuaderno.borrar_plantilla_confirmar', { nombre: p.name }), danger: true })) borrarPlantilla.mutate(p.key) }}>
                  <Trash2 size={14} />
                </IconButton>
              )}
            </li>
          ))}
        </ul>
      </Section>

      {puede('cuaderno.acceso_excepcional') && (
        <Section title={<span className="cdn-seccion"><ShieldAlert size={15} />{t('cuaderno.excepcional')}</span>} subtitle={t('cuaderno.excepcional_d')}>
          <AccesoExcepcional />
        </Section>
      )}
      {editando && <ModalPlantilla plantilla={editando === 'nueva' ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  )
}
