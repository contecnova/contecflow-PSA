/**
 * Tipos de documento de ausencias (parte de baja, parte de confirmación,
 * justificante…): nombre por idioma y si es de categoría especial (salud).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, ShieldAlert, Trash2 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { TipoDeDocumentoIn } from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner, Pulsable } from '../../ui'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { AvisoDeError, Casilla, NombresPorIdioma, errorDe, nombreEn, useT } from './comun'

const NUEVO: TipoDeDocumentoIn = { clave: '', nombre: '', nombres: {}, categoria_especial: false, activo: true, orden: 100 }

export default function EditorDeDocumentos() {
  const { ta, lang } = useT()
  const [abierto, setAbierto] = useState<{ id: string | null; datos: TipoDeDocumentoIn } | null>(null)
  const q = useQuery({ queryKey: ['ausencias', 'documentos', 'todos'], queryFn: () => ausenciasApi.documentos(true) })
  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  const docs = q.data ?? []
  return (
    <section aria-labelledby="ausadm-docs-titulo">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-docs-titulo" className="ausadm-titulo">{ta('documentos_titulo')}</h2>
        <Button icon={<Plus size={14} />} onClick={() => setAbierto({ id: null, datos: { ...NUEVO } })}>{ta('nuevo_documento')}</Button>
      </div>
      <p className="ausadm-ayuda">{ta('documentos_ayuda')}</p>
      {docs.length === 0
        ? <EmptyState svgIcon={<FileText size={26} />} title={ta('sin_documentos')} ctaLabel={ta('nuevo_documento')}
            onCta={() => setAbierto({ id: null, datos: { ...NUEVO } })} />
        : (
          <ul className="ausadm-lista">
            {docs.map(d => (
              <li key={d.id}>
                <Pulsable className={`ausadm-item${d.activo ? '' : ' ausadm-item--inactivo'}`}
                  onClick={() => { const { id: _id, ...resto } = d; setAbierto({ id: d.id, datos: resto }) }}>
                  <FileText size={16} aria-hidden />
                  <span className="ausadm-item-nombre">{nombreEn(d, lang)} <span className="ausadm-ayuda">({d.clave})</span></span>
                  <span className="ausadm-chips">
                    {d.categoria_especial && <span className="ausadm-chip ausadm-chip--aviso"><ShieldAlert size={12} aria-hidden /> {ta('categoria_especial')}</span>}
                    {!d.activo && <span className="ausadm-chip">{ta('inactivo')}</span>}
                  </span>
                </Pulsable>
              </li>
            ))}
          </ul>
        )}
      {abierto && <Formulario key={abierto.id ?? 'nuevo'} id={abierto.id} inicial={abierto.datos} onCerrar={() => setAbierto(null)} />}
    </section>
  )
}

function Formulario({ id, inicial, onCerrar }: { id: string | null; inicial: TipoDeDocumentoIn; onCerrar: () => void }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [d, setD] = useState(inicial)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const guardar = useMutation({
    mutationFn: () => (id ? ausenciasApi.guardarDocumento(id, d) : ausenciasApi.crearDocumento(d)),
    onSuccess: () => { toast.success(ta('guardado')); refrescar(); onCerrar() },
  })
  const borrar = useMutation({
    mutationFn: () => ausenciasApi.borrarDocumento(id as string),
    onSuccess: r => { toast.success(r.desactivado ? ta('desactivado_en_uso') : ta('borrado')); refrescar(); onCerrar() },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  return (
    <Modal open onClose={onCerrar} title={id ? ta('editar_documento') : ta('nuevo_documento')}>
      <form className="ausadm-form" onSubmit={e => { e.preventDefault(); guardar.mutate() }}>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('clave')}</span>
            <input aria-label={ta('clave')} className="ausadm-campo" required pattern="[a-z0-9_]{2,50}" value={d.clave}
              onChange={e => setD({ ...d, clave: e.target.value.toLowerCase() })} />
            <span className="ausadm-ayuda">{ta('clave_ayuda')}</span>
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('nombre_principal')}</span>
            <input aria-label={ta('nombre_principal')} className="ausadm-campo" value={d.nombre} onChange={e => setD({ ...d, nombre: e.target.value })} />
          </label>
        </div>
        <NombresPorIdioma valor={d.nombres} onChange={nombres => setD({ ...d, nombres })} />
        <Casilla etiqueta={ta('categoria_especial')} ayuda={ta('categoria_especial_ayuda')} valor={d.categoria_especial}
          onChange={v => setD({ ...d, categoria_especial: v })} />
        <Casilla etiqueta={ta('activo')} valor={d.activo} onChange={v => setD({ ...d, activo: v })} />
        <AvisoDeError error={guardar.error} defecto={ta('error_guardar')} />
        <div className="ausadm-acciones">
          {id && <Button variant="danger" icon={<Trash2 size={14} />} loading={borrar.isPending}
            onClick={async () => { if (await confirmar({ title: ta('borrar'), danger: true, message: ta('borrar_documento_confirmar') })) borrar.mutate() }}>
            {ta('borrar')}</Button>}
          <Button variant="secondary" onClick={onCerrar}>{ta('cancelar')}</Button>
          <Button type="submit" loading={guardar.isPending}>{ta('guardar')}</Button>
        </div>
      </form>
    </Modal>
  )
}
