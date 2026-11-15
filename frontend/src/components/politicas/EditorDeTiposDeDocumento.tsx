/**
 * Tipos de documento que una regla puede exigir (rev. 166, tarea #27): la lista
 * `POLICY_DOCUMENT_TYPES` de la empresa, editada con chips (nadie escribe CSV).
 * Cada justificante de gasto lleva uno; `require_attachment` pide alguno de
 * ellos. Un tipo en uso (política vigente o justificante) no se puede quitar.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Save } from 'lucide-react'
import { politicasApi } from '../../services/api'
import { Button, Spinner } from '../ui'
import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { ListaDeValores, useTextos } from './comun'

export default function EditorDeTiposDeDocumento() {
  const { t } = useTextos()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['politicas', 'tipos-de-documento'], queryFn: politicasApi.tiposDeDocumento })
  const [tipos, setTipos] = useState<string[]>([])
  useEffect(() => { if (q.data) setTipos(q.data.tipos) }, [q.data])
  const guardar = useMutation({
    mutationFn: () => politicasApi.guardarTiposDeDocumento(tipos),
    onSuccess: d => {
      setTipos(d.tipos)
      qc.invalidateQueries({ queryKey: ['politicas'] })
      toast.success(t('pol.tipos_guardados'))
    },
    onError: e => toast.error(extractErr(e, t('pol.error_guardar'))),
  })
  if (q.isLoading) return <Spinner label={t('pol.cargando')} />
  if (q.isError) return <div role="alert" className="pol-error">{extractErr(q.error, t('pol.error_cargar'))}</div>
  const cambiado = JSON.stringify(tipos) !== JSON.stringify(q.data?.tipos ?? [])
  return (
    <section className="pol-tarjeta" aria-labelledby="pol-tipos-doc">
      <h3 id="pol-tipos-doc" className="pol-titulo"><FileText size={16} aria-hidden /> {t('pol.tipos_de_documento')}</h3>
      <p className="pol-ayuda">{t('pol.tipos_de_documento_ayuda')}</p>
      <ListaDeValores valores={tipos} onChange={v => setTipos(v.map(x => x.trim().toLowerCase()))} opciones={[]} libre
        etiqueta={t('pol.anadir_tipo_de_documento')} mostrar={d => t(`pol.doc_${d}`, d)} />
      {!tipos.length && <p className="pol-error" role="alert">{t('pol.tipos_minimo_uno')}</p>}
      <div className="pol-fila-fin pol-mt">
        <Button icon={<Save size={14} />} disabled={!cambiado || !tipos.length} loading={guardar.isPending} onClick={() => guardar.mutate()}>
          {t('pol.guardar')}
        </Button>
      </div>
    </section>
  )
}
