/**
 * Biblioteca de marcos y controles (§3.1): un control implantado una vez cuenta para todas las
 * normas que lo exigen. Muestra la descripción propia y, si la empresa lo importó con su
 * licencia, el texto oficial; marca lo afectado por un cambio de versión. Administración:
 * validación del contenido, sembrar/poner al día e importar el texto oficial (CSV o JSON).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, RefreshCw, Upload } from 'lucide-react'
import { Button, Buscador, Card, Checkbox, FiltrosDeLista, Modal, SelectRico, Tabla, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Control, Marco } from '../../services/api/certificaciones'
import { etiquetaNivel } from './comun'

export default function CatalogoCert() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const administrar = puede('certificaciones.administrar')
  const [marco, setMarco] = useState('')
  const [q, setQ] = useState('')
  const [afectados, setAfectados] = useState(false)
  const [abierto, setAbierto] = useState<Control | null>(null)
  const [importar, setImportar] = useState(false)
  const filtros = { marco: marco || undefined, q: q || undefined, afectados: afectados || undefined }
  const { data: marcos = [] } = useQuery({ queryKey: CLAVES_CERT.marcos, queryFn: certApi.marcos })
  const { data: controles = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.controles(filtros), queryFn: () => certApi.controles(filtros) })
  const { data: validacion } = useQuery({ queryKey: CLAVES_CERT.validacion, queryFn: certApi.validacion, enabled: administrar })
  const sembrar = useMutation({
    mutationFn: certApi.sembrar,
    onSuccess: r => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo });
      toast.success(t('cert.sembrado', { c: r.controles_creados + r.controles_actualizados, r: r.correspondencias_creadas })) },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <div className="u-stack-16">
      <Tabla<Marco> etiqueta={t('cert.marcos')} filas={marcos}
        columnas={[
          { key: 'nombre', label: t('cert.marco'), cabeceraDeFila: true },
          { key: 'version', label: t('cert.version'), render: (_v, m) => (
            <div className="cert-celda"><span>{m.version ?? '—'}</span>
              {m.version_anterior && <span className="cert-apagado">{t('cert.antes', { version: m.version_anterior })}</span>}</div>) },
          { key: 'publico', label: t('cert.texto'), render: (_v, m) => (m.publico ? t('cert.texto_publico') : t('cert.texto_con_licencia')) },
          { key: 'niveles', label: t('cert.niveles'), render: (_v, m) => m.niveles.map(n => etiquetaNivel(t, n)).join(', ') || '—' },
          { key: 'controles', label: t('cert.controles'), alinear: 'derecha' },
        ]} />
      {administrar && validacion && (
        <Card>
          <div className="cert-acciones">
            <span>{t('cert.validacion_resumen', { m: validacion.marcos, c: validacion.controles, p: validacion.plantillas, d: validacion.documentos })}</span>
            {validacion.errores.length > 0 && <span className="cert-aviso cert-aviso--peligro">{t('cert.validacion_errores', { n: validacion.errores.length })}</span>}
            <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={sembrar.isPending} onClick={() => sembrar.mutate()}>
              {t('cert.sembrar')}</Button>
            <Button size="sm" variant="secondary" icon={<Upload size={14} />} onClick={() => setImportar(true)}>{t('cert.importar_texto')}</Button>
          </div>
          {validacion.errores.length > 0 && <pre className="cert-texto">{validacion.errores.slice(0, 20).join('\n')}</pre>}
        </Card>
      )}
      <FiltrosDeLista aria-label={t('cert.filtros')}
        buscador={<Buscador value={q} onChange={setQ} retardo={300} placeholder={t('cert.buscar_control')} />}>
        <SelectRico aria-label={t('cert.marco')} valor={marco} onChange={setMarco} opciones={[
          { valor: '', etiqueta: t('cert.todos_los_marcos') }, ...marcos.map(m => ({ valor: m.clave, etiqueta: m.nombre }))]} />
      </FiltrosDeLista>
      <Checkbox checked={afectados} onChange={setAfectados} label={t('cert.solo_afectados')} />
      <Tabla<Control> etiqueta={t('cert.controles')} filas={controles} cargando={isLoading} ordenable onFila={setAbierto}
        vacio={{ icono: <BookOpen size={28} />, titulo: t('cert.sin_controles') }}
        columnas={[
          { key: 'clave_comun', label: t('cert.control'), cabeceraDeFila: true, render: (_v, c) => (
            <div className="cert-celda"><span>{c.titulo}</span><span className="cert-apagado">{c.clave_comun}</span></div>) },
          { key: 'dominio', label: t('cert.dominio'), render: (_v, c) => (c.dominio ? t(`cert.dominio_${c.dominio}`) : '—') },
          { key: 'correspondencias', label: t('cert.correspondencias'), sortable: false, render: (_v, c) => (
            <div className="cert-marcos">{c.correspondencias.map(r => (
              <span key={r.id} className="cert-apagado">{r.marco ? t(`cert.marco_${r.marco}`) : '?'} {r.id_control}{r.afectado_por_version ? ' ⚠' : ''}</span>))}</div>) },
          { key: 'medible_por_plataforma', label: t('cert.medible'), render: (_v, c) => (c.medible_por_plataforma ? t('cert.si') : '—') },
        ]} />
      {abierto && <FichaControl control={abierto} onClose={() => setAbierto(null)} />}
      {importar && <ImportarTexto onClose={() => setImportar(false)} />}
    </div>
  )
}

function FichaControl({ control: c, onClose }: { control: Control; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const revisar = useMutation({ mutationFn: (id: string) => certApi.revisada(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }), onError: e => toast.error(extractErr(e)) })
  return (
    <Modal open title={c.titulo} subtitle={c.clave_comun} onClose={onClose} size="lg" avisarSinGuardar={false}>
      <div className="u-stack-12">
        <p className="cert-texto">{c.descripcion}</p>
        {c.evidencia_sugerida.length > 0 && (
          <div><strong>{t('cert.evidencia_sugerida')}</strong><ul>{c.evidencia_sugerida.map(x => <li key={x}>{x}</li>)}</ul></div>)}
        <Tabla etiqueta={t('cert.correspondencias')} filas={c.correspondencias}
          columnas={[
            { key: 'marco', label: t('cert.marco'), render: (_v, r) => (r.marco ? t(`cert.marco_${r.marco}`) : '—') },
            { key: 'id_control', label: t('cert.identificador'), render: (_v, r) => (
              <div className="cert-celda"><span>{r.id_control}</span>
                {r.id_semilla && r.id_semilla !== r.id_control && <span className="cert-apagado">{t('cert.antes', { version: r.id_semilla })}</span>}</div>) },
            { key: 'nivel', label: t('cert.nivel'), render: (_v, r) => etiquetaNivel(t, r.nivel) },
            { key: 'texto_oficial', label: t('cert.texto_oficial'), render: (_v, r) => (r.texto_oficial
              ? <span className="cert-texto">{r.texto_oficial}</span> : <span className="cert-apagado">{t('cert.sin_texto_oficial')}</span>) },
            { key: 'afectado', label: t('cert.version'), sortable: false, render: (_v, r) => (r.afectado_por_version
              ? (puede('certificaciones.administrar')
                ? <Button size="xs" variant="secondary" onClick={() => revisar.mutate(r.id)}>{t('cert.marcar_revisada')}</Button>
                : t('cert.afectado_por_version'))
              : '—') },
          ]} />
      </div>
    </Modal>
  )
}

/** CSV `marco;id_control;texto_oficial[;id_control_nuevo]` o JSON `[{marco, id_control, texto_oficial, id_control_nuevo}]`. */
function ImportarTexto({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [texto, setTexto] = useState('')
  const [titular, setTitular] = useState('')
  const filas = (): Record<string, unknown>[] => {
    const s = texto.trim()
    if (s.startsWith('[')) return JSON.parse(s) as Record<string, unknown>[]
    return s.split(/\r?\n/).filter(Boolean).map(l => {
      const [marco, id_control, texto_oficial, id_control_nuevo] = l.split(';')
      return { marco: marco?.trim(), id_control: id_control?.trim(), texto_oficial: texto_oficial ?? null,
        id_control_nuevo: id_control_nuevo?.trim() || undefined }
    })
  }
  const importar = useMutation({
    mutationFn: () => certApi.importarTexto(filas(), { titular }),
    onSuccess: r => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo });
      toast.success(t('cert.importado', { a: r.actualizados, r: r.renombrados, s: r.sin_casar.length })); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.importar_texto')} subtitle={t('cert.importar_texto_ayuda')} onClose={onClose} size="lg"
      cambiosSinGuardar={!!texto}>
      <div className="u-stack-12">
        <Textarea label={t('cert.licencia_titular')} value={titular} rows={1} onChange={e => setTitular(e.target.value)} />
        <Textarea label={t('cert.contenido_a_importar')} value={texto} rows={12} onChange={e => setTexto(e.target.value)} />
        <div className="cert-acciones">
          <Button disabled={!texto.trim()} loading={importar.isPending} onClick={() => importar.mutate()}>{t('cert.importar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
