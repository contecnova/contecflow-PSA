/**
 * Panel lateral de notas rápidas (icono de la barra superior, junto al chat y
 * el calendario): apuntar algo desde cualquier pantalla sin salir de ella. Las
 * notas rápidas viven en el cuaderno «Notas rápidas» de la persona (privado,
 * no se comparte); también se ven las páginas recientes. Se guarda solo.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink, NotebookPen, Plus, X } from 'lucide-react'
import { Button, Drawer, EmptyState, IconButton, Pulsable, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'
import type { RapidaCorta } from '../../services/api/cuaderno'
import EditorDeNota from './EditorDeNota'
import { useSinRed } from './useSinRed'
import './cuaderno.css'

export default function PanelRapido({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [abierta, setAbierta] = useState<string | null>(null)
  useSinRed()
  const { data, isLoading } = useQuery({ queryKey: CLAVES_CUADERNO.rapidas, queryFn: cuadernoApi.rapidas })
  const { data: arbol } = useQuery({ queryKey: CLAVES_CUADERNO.arbol, queryFn: cuadernoApi.arbol, staleTime: 60_000 })

  const nueva = async () => {
    try {
      const p = await cuadernoApi.nuevaRapida({})
      void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.rapidas })
      setAbierta(p.id)
    } catch (e) { toast.error(extractErr(e)) }
  }
  const fila = (x: RapidaCorta) => (
    <li key={x.id}>
      <Pulsable className="cdn-rapida" onClick={() => setAbierta(x.id)}>
        <strong>{x.title || t('cuaderno.sin_titulo')}</strong>
        {x.snippet && <span className="cdn-resultado__fragmento">{x.snippet}</span>}
        <span className="cdn-lista__sub">{fmtDateTime(x.updated_at)}</span>
      </Pulsable>
    </li>
  )

  return (
    <Drawer onClose={onClose} ariaLabel={t('cuaderno.notas_rapidas')} width={460} variant="borde" avisarSinGuardar={false}>
      <div className="cdn-panel">
        <div className="cdn-panel__cabecera">
          {abierta
            ? <IconButton ariaLabel={t('cuaderno.volver')} onClick={() => { setAbierta(null); void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.rapidas }) }} className="cdn-boton"><ArrowLeft size={15} /></IconButton>
            : <NotebookPen size={16} aria-hidden />}
          <h2 className="cdn-panel__titulo">{t('cuaderno.notas_rapidas')}</h2>
          {abierta && <IconButton ariaLabel={t('cuaderno.abrir_en_cuaderno')} title={t('cuaderno.abrir_en_cuaderno')} className="cdn-boton"
            onClick={() => { navigate(`/notebook?page=${abierta}`); onClose() }}><ExternalLink size={15} /></IconButton>}
          <IconButton ariaLabel={t('common.close')} onClick={onClose} className="cdn-boton"><X size={15} /></IconButton>
        </div>
        {abierta ? (
          <EditorDeNota key={abierta} pageId={abierta} etiquetas={arbol?.tags ?? []} funciones={arbol?.features} compacto
            onBorrada={() => setAbierta(null)} />
        ) : (
          <div className="cdn-panel__cuerpo">
            <Button icon={<Plus size={14} />} onClick={() => { void nueva() }}>{t('cuaderno.nueva_nota_rapida')}</Button>
            {isLoading ? <Spinner /> : (
              <>
                {(data?.quick.length ?? 0) === 0
                  ? <EmptyState icon={<NotebookPen size={28} />} title={t('cuaderno.sin_rapidas')} description={t('cuaderno.sin_rapidas_ayuda')} />
                  : <ul className="cdn-rapidas">{data?.quick.map(fila)}</ul>}
                {(data?.recent.length ?? 0) > 0 && (
                  <>
                    <h3 className="ds-eyebrow">{t('cuaderno.recientes')}</h3>
                    <ul className="cdn-rapidas">{data?.recent.map(fila)}</ul>
                  </>
                )}
              </>
            )}
            <Button variant="link" onClick={() => { navigate('/notebook'); onClose() }}>{t('cuaderno.ir_al_cuaderno')}</Button>
          </div>
        )}
      </div>
    </Drawer>
  )
}
