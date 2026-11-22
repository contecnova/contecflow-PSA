/**
 * Sección «Flujos de demanda» de Configuración (`/settings/demanda`, 22-11-2026).
 *
 * Tipos de solicitud (canales, proyecto, flujo) y flujos (definición por fases
 * en JSON versionado). Rutas: `/api/v1/demand/types` y `/demand/flows`
 * (capacidad `demanda.config`). Cada guardado de un flujo sube su versión;
 * los expedientes en curso conservan la foto con la que nacieron.
 * Ver docs/FLUJO_DE_DEMANDA.md.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Plus, Sparkles } from 'lucide-react'
import { Button, Checkbox, GrupoDeOpciones, Input, Modal, Select, Spinner, StatusBadge, Tabs, TablaSimple } from '../ui'
import { demandaApi, type TipoDeDemanda, type TextoI18n } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CamposI18n, etiquetaDe, opcionesDe, useCatalogoDemanda } from './comunes'
import { claveDesdeTexto, claveValida } from './utilDemanda'
import EditorDeFlujo from './EditorDeFlujo'
import '../planificador/planificador.css'
import './demanda.css'

const CANALES_POR_DEFECTO = ['client_portal', 'internal_portal', 'operator', 'supplier_portal']
const AMBITOS_POR_DEFECTO = ['project', 'service', 'asset', 'none']

function FormularioDeTipo({ tipo, onClose }: { tipo: TipoDeDemanda | null; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const catalogo = useCatalogoDemanda()
  const { data: flujos = [] } = useQuery({ queryKey: ['demand-flows'], queryFn: demandaApi.flujos })
  const canales = catalogo.channels.length ? catalogo.channels : CANALES_POR_DEFECTO
  const todosAmbitos = catalogo.scopes?.length ? catalogo.scopes : AMBITOS_POR_DEFECTO
  const [clave, setClave] = useState(tipo?.key ?? '')
  const [nombres, setNombres] = useState<TextoI18n>(tipo?.name_i18n ?? { es: tipo?.name ?? '', en: '', zh: '' })
  const [canalesElegidos, setCanales] = useState<string[]>(tipo?.channels ?? ['client_portal'])
  const [exigeProyecto, setExigeProyecto] = useState(tipo?.requires_project ?? false)
  const [independiente, setIndependiente] = useState(tipo?.allows_standalone ?? false)
  const [flujo, setFlujo] = useState(tipo?.flow_id ?? '')
  const [ambitos, setAmbitos] = useState<string[]>(tipo?.scopes ?? ['project'])
  const [descripcion, setDescripcion] = useState(tipo?.description ?? '')
  const [activo, setActivo] = useState(tipo?.is_active ?? true)
  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        key: clave.trim(), name: nombres.es?.trim() || clave.trim(), name_i18n: nombres, channels: canalesElegidos,
        requires_project: exigeProyecto, allows_standalone: independiente && !exigeProyecto, flow_id: flujo || null, is_active: activo,
        scopes: ambitos, description: descripcion.trim() || null,
      }
      return tipo ? demandaApi.editarTipo(tipo.id, cuerpo) : demandaApi.crearTipo(cuerpo)
    },
    onSuccess: () => { toast.success(t('demanda.cfg_tipo_guardado')); qc.invalidateQueries({ queryKey: ['demand-types'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const falta = !claveValida(clave.trim()) || !nombres.es?.trim() || canalesElegidos.length === 0
  return (
    <Modal open onClose={onClose} size="lg" title={tipo ? t('demanda.cfg_editar_tipo') : t('demanda.cfg_nuevo_tipo')}>
      <div className="u-stack-16">
        <Input label={t('demanda.cfg_clave')} required inputClassName="u-mono dem-mono" disabled={!!tipo} value={clave} hint={t('demanda.cfg_clave_tipo_ayuda')}
          error={clave && !claveValida(clave) ? t('demanda.cfg_clave_invalida') : undefined}
          onChange={e => setClave(e.target.value)} onBlur={() => { if (!clave && nombres.es) setClave(claveDesdeTexto(nombres.es)) }} />
        <CamposI18n etiqueta={t('demanda.cfg_nombre')} valor={nombres} requeridoEs onChange={setNombres} />
        <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_canales')} valor={canalesElegidos} onChange={setCanales}
          opciones={opcionesDe(t, 'canal', canales).map(o => ({ valor: o.value, titulo: o.label }))} />
        <Input label={t('demanda.cfg_descripcion')} value={descripcion} onChange={e => setDescripcion(e.target.value)} />
        <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_ambitos')} valor={ambitos} onChange={setAmbitos}
          opciones={opcionesDe(t, 'ambito', todosAmbitos).map(o => ({ valor: o.value, titulo: o.label }))} />
        <Checkbox label={t('demanda.cfg_exige_proyecto')} ayuda={t('demanda.cfg_exige_proyecto_ayuda')} checked={exigeProyecto} onChange={setExigeProyecto} />
        <Checkbox label={t('demanda.cfg_permite_independiente')} ayuda={t('demanda.cfg_permite_independiente_ayuda')} disabled={exigeProyecto} checked={independiente && !exigeProyecto} onChange={setIndependiente} />
        <Select label={t('demanda.cfg_flujo')} value={flujo} onChange={e => setFlujo(e.target.value)} options={flujos.map(f => ({ value: f.id, label: `${f.name} (v${f.version})` }))} />
        <Checkbox label={t('demanda.cfg_activo')} checked={activo} onChange={setActivo} />
        <div className="dem-acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardar.isPending} disabled={falta} onClick={() => guardar.mutate()}>{t('demanda.cfg_guardar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function TiposDeSolicitud() {
  const t = useAppT()
  const [editando, setEditando] = useState<TipoDeDemanda | 'nuevo' | null>(null)
  const { data: tipos = [], isLoading } = useQuery({ queryKey: ['demand-types'], queryFn: demandaApi.tipos })
  return (
    <div className="ds-card u-stack-16">
      <div className="dem-fila dem-fila--entre">
        <h3 className="plan-card__titulo">{t('demanda.cfg_tipos')}</h3>
        <Button size="xs" icon={<Plus size={12} />} onClick={() => setEditando('nuevo')}>{t('demanda.cfg_nuevo_tipo')}</Button>
      </div>
      <p className="plan-muted">{t('demanda.cfg_tipos_ayuda')}</p>
      {isLoading ? <Spinner /> : tipos.length === 0 ? <p className="plan-muted">{t('demanda.cfg_sin_tipos')}</p> : (
        <TablaSimple claseTabla="plan-tabla">
          <thead><tr><th>{t('demanda.cfg_clave')}</th><th>{t('demanda.cfg_nombre')}</th><th>{t('demanda.cfg_canales')}</th><th>{t('demanda.proyecto')}</th><th>{t('demanda.cfg_flujo')}</th><th>{t('demanda.cfg_activo')}</th><th /></tr></thead>
          <tbody>
            {tipos.map(x => (
              <tr key={x.id}>
                <td className="u-mono dem-mono">{x.key}</td>
                <td>{x.name}</td>
                <td>{x.channels.map(c => etiquetaDe(t, 'canal', c)).join(', ')}</td>
                <td>{x.requires_project ? t('demanda.cfg_exige_proyecto_corta') : x.allows_standalone ? t('demanda.cfg_proyecto_o_independiente') : t('demanda.cfg_proyecto_opcional')}</td>
                <td>{x.flow_name ?? (x.flow_id ? x.flow_id : '—')}</td>
                <td><StatusBadge kind={x.is_active ? 'success' : 'neutral'}>{x.is_active ? t('demanda.cfg_si') : t('demanda.cfg_no')}</StatusBadge></td>
                <td><Button size="xs" variant="subtle" onClick={() => setEditando(x)}>{t('demanda.cfg_editar')}</Button></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
      {editando && <FormularioDeTipo tipo={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  )
}

function ListaDeFlujos({ onEditar }: { onEditar: (id: string | null) => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: flujos = [], isLoading } = useQuery({ queryKey: ['demand-flows'], queryFn: demandaApi.flujos })
  const piloto = useMutation({
    mutationFn: demandaApi.plantillaPiloto,
    onSuccess: () => { toast.success(t('demanda.cfg_piloto_cargada')); qc.invalidateQueries({ queryKey: ['demand-flows'] }); qc.invalidateQueries({ queryKey: ['demand-types'] }) },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const { data: plantillas = [] } = useQuery({ queryKey: ['demand-templates'], queryFn: demandaApi.plantillas })
  const instalar = useMutation({
    mutationFn: (key: string) => demandaApi.instalarPlantilla(key),
    onSuccess: r => { toast.success(t(r.created ? 'demanda.cfg_plantilla_instalada' : 'demanda.cfg_plantilla_ya_instalada')); qc.invalidateQueries({ queryKey: ['demand-flows'] }); qc.invalidateQueries({ queryKey: ['demand-types'] }) },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const [claveImportar, setClaveImportar] = useState(0)
  const importar = useMutation({
    mutationFn: async (f: File) => demandaApi.importarFlujo(JSON.parse(await f.text())),
    onSuccess: () => { toast.success(t('demanda.cfg_importado')); setClaveImportar(n => n + 1); qc.invalidateQueries({ queryKey: ['demand-flows'] }); qc.invalidateQueries({ queryKey: ['demand-types'] }) },
    onError: (e: unknown) => toast.error(e instanceof SyntaxError ? t('demanda.cfg_json_invalido') : extractErr(e, t('demanda.error'))),
  })
  return (
    <div className="ds-card u-stack-16">
      <div className="dem-bloque">
        <div className="dem-bloque__titulo">{t('demanda.cfg_biblioteca')}</div>
        <p className="plan-muted">{t('demanda.cfg_biblioteca_ayuda')}</p>
        {plantillas.length === 0 ? <p className="plan-muted">{t('demanda.cfg_sin_plantillas')}</p> : (
          <TablaSimple claseTabla="plan-tabla">
            <thead><tr><th>{t('demanda.cfg_nombre')}</th><th>{t('demanda.cfg_descripcion')}</th><th /></tr></thead>
            <tbody>
              {plantillas.map(x => (
                <tr key={x.key}>
                  <td>{x.name}</td><td>{x.description}</td>
                  <td><Button size="xs" variant="subtle" icon={<Download size={12} />} loading={instalar.isPending && instalar.variables === x.key} onClick={() => instalar.mutate(x.key)}>{t('demanda.cfg_instalar')}</Button></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
        <Input key={claveImportar} label={t('demanda.cfg_importar')} hint={t('demanda.cfg_importar_ayuda')} type="file" accept=".json,application/json"
          onChange={e => { const f = e.target.files?.[0]; if (f) importar.mutate(f) }} />
        {importar.isPending && <Spinner />}
      </div>
      <div className="dem-fila dem-fila--entre">
        <h3 className="plan-card__titulo">{t('demanda.cfg_flujos')}</h3>
        <span className="dem-fila">
          <Button size="xs" variant="secondary" icon={<Sparkles size={12} />} loading={piloto.isPending} onClick={() => piloto.mutate()}>{t('demanda.cfg_cargar_piloto')}</Button>
          <Button size="xs" icon={<Plus size={12} />} onClick={() => onEditar(null)}>{t('demanda.cfg_nuevo_flujo')}</Button>
        </span>
      </div>
      <p className="plan-muted">{t('demanda.cfg_piloto_ayuda')}</p>
      {isLoading ? <Spinner /> : flujos.length === 0 ? <p className="plan-muted">{t('demanda.cfg_sin_flujos')}</p> : (
        <TablaSimple claseTabla="plan-tabla">
          <thead><tr><th>{t('demanda.cfg_nombre')}</th><th className="plan-num">{t('demanda.cfg_version_corta')}</th><th>{t('demanda.cfg_activo')}</th><th /></tr></thead>
          <tbody>
            {flujos.map(f => (
              <tr key={f.id}>
                <td>{f.name}</td><td className="plan-num">{f.version}</td>
                <td><StatusBadge kind={f.is_active ? 'success' : 'neutral'}>{f.is_active ? t('demanda.cfg_si') : t('demanda.cfg_no')}</StatusBadge></td>
                <td><Button size="xs" variant="subtle" onClick={() => onEditar(f.id)}>{t('demanda.cfg_editar')}</Button></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
    </div>
  )
}

export default function ConfigDemanda() {
  const t = useAppT()
  const [tab, setTab] = useState<'tipos' | 'flujos'>('flujos')
  // `undefined`: lista; `null`: flujo nuevo; texto: id del flujo abierto.
  const [flujo, setFlujo] = useState<string | null | undefined>(undefined)
  if (flujo !== undefined) return <EditorDeFlujo key={flujo ?? 'nuevo'} flujoId={flujo} onVolver={() => setFlujo(undefined)} />
  return (
    <div className="u-stack-16">
      <Tabs ariaLabel={t('demanda.cfg_secciones')} active={tab} onChange={s => setTab(s as 'tipos' | 'flujos')}
        items={[{ id: 'flujos', label: t('demanda.cfg_flujos') }, { id: 'tipos', label: t('demanda.cfg_tipos') }]} />
      {tab === 'flujos' ? <ListaDeFlujos onEditar={setFlujo} /> : <TiposDeSolicitud />}
    </div>
  )
}
