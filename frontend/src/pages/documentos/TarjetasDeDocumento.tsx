/**
 * Tarjeta y fila de documento con su chip de reserva.
 * Troceado de DocumentsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { useState, type CSSProperties } from 'react'
import { sanitizeUrl } from '../../utils/security'
import { useAuth } from '../../context/AuthContext'
import { Download, Trash2, Sparkles, History, Check, Lock } from 'lucide-react'
import { Pulsable, IconButton } from '../../components/ui'
import { fmtDate, fmtDateTime } from '../../utils/helpers'
import {
  CAT_STYLE,
  Chip,
  ChipAprobacion,
  detectFileType,
  type DocItemProps,
  etiquetaCategoria,
  FILE_COLORS,
  FileIcon,
  fmtBytes,
  relTime,
  type Reserva,
} from './compartido'

/** Quién tiene el documento reservado para editar (revisión 2026-11). */
function ReservaChip({ reserva }: { reserva: Reserva }) {
  const t = useAppT()
  const { user } = useAuth()
  if (!reserva) return null
  // Los listados mandan la reserva sin `mine` (reserva_de_documentos.vigente): se deduce.
  const mia = reserva.mine ?? reserva.user_id === user?.id
  return (
    <div title={reserva.expires_at ? t('documents.reserva_hasta', { fecha: fmtDateTime(reserva.expires_at) }) : undefined}
      className={`docs-row-5 ${mia ? 'document-sx6' : 'document-sx7'}`}>
      <Lock size={10} /> {mia ? t('documents.reserva_tuya') : t('documents.reserva_de', { nombre: reserva.user_name || '—' })}
    </div>
  )
}

export function DocCard({ doc, onView, onDelete, onSummary, selected, onToggleSelect }: DocItemProps) {
  const { t } = useAppLang()
  const [hover, setHover] = useState(false);
  const lv = doc.latest_version;
  const type = detectFileType(lv?.file_mime_type, lv?.file_name);
  const ft = FILE_COLORS[type];
  const catS = CAT_STYLE[doc.category] || CAT_STYLE.other;

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onView(doc.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onView(doc.id);
        }
      }}
      className={`docs-stack document-sx8 ${hover ? 'document-sx9' : 'document-sx10'} documents-page-e4`} style={{ '--documents-page-border': `1px solid ${selected ? 'var(--accent)' : hover ? 'var(--surface-5)' : 'var(--surface-4)'}` } as CSSProperties}>

      {/* Top color strip */}
      <div className="docs-box-4 documents-page-e3" style={{ '--documents-page-background-color': ft.c } as CSSProperties} />

      {/* Checkbox */}
      <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: casilla de selección de la tarjeta */
        type="button"
        onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }}
        className={`docs-btn document-sx11 ${selected ? 'document-sx12' : 'document-sx13'} ${selected || hover ? 'document-sx14' : 'document-sx15'} documents-page-e4`} style={{ '--documents-page-border': `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
        {selected && <Check size={9} color="white" strokeWidth={3} />}
      </Pulsable>

      {/* Body */}
      <div className="docs-stack-2">
        <div className="docs-row-6">
          <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={42} />
          <div className="u-flex1-min0">
            <div className="docs-box-5">{doc.title}</div>
            <ReservaChip reserva={doc.checkout} />
            {lv?.file_name && (
              <div className="docs-box-6">
                {lv.file_name}
              </div>
            )}
          </div>
        </div>

        {/* Badges */}
        <div className="docs-row-7">
          <Chip text={etiquetaCategoria(t, doc.category)} color={catS.c} bg={catS.bg} />
          {doc.requires_approval && <ChipAprobacion estado={doc.approval_status} />}
          {(doc.version_count || 0) > 1 && (
            <span className="docs-row-8">
              <History size={9} /> v{doc.version_count}
            </span>
          )}
        </div>

        {/* Tags */}
        {doc.tags?.length > 0 && (
          <div className="docs-row-9">
            {doc.tags.slice(0, 3).map(t => (
              <span key={t} className="docs-label">
                #{t}
              </span>
            ))}
            {doc.tags.length > 3 && <span className="u-text3-2xs">+{doc.tags.length - 3}</span>}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="docs-row-10">
        <div>
          <div className="u-text3-2xs">{relTime(doc.created_at)}</div>
          {lv && <div className="docs-box-7">{fmtBytes(lv.file_size)}</div>}
        </div>
        <div className={`docs-row-11 ${hover ? 'document-sx14' : 'document-sx15'}`}>
          {lv?.download_url && (
            <a href={sanitizeUrl(lv.download_url)} target="_blank" rel="noreferrer" title={t('pagina_docs.descargar_documento')} aria-label={t('pagina_docs.descargar_documento')}
              onClick={e => e.stopPropagation()}
              className="docs-link">
              <Download size={11} />
            </a>
          )}
          <IconButton variante="caja" tono="acento" ariaLabel={t('pagina_docs.generar_resumen_ia')} onClick={(e) => { e.stopPropagation(); onSummary(doc.id); }} title={t('pagina_docs.generar_resumen_ia')}>
            <Sparkles size={11} />
          </IconButton>
          <IconButton variante="caja" tono="peligro" ariaLabel={t('pagina_docs.eliminar_documento')} onClick={(e) => { e.stopPropagation(); onDelete(doc); }} title={t('pagina_docs.eliminar_documento')}>
            <Trash2 size={11} />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

// ── Doc Row (Table) ─────────────────────────────────────────

export function DocRow({ doc, onView, onDelete, onSummary, selected, onToggleSelect }: DocItemProps) {
  const t = useAppT();
  const [hover, setHover] = useState(false);
  const lv = doc.latest_version;
  const catS = CAT_STYLE[doc.category] || CAT_STYLE.other;

  return (
    <tr
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onView(doc.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onView(doc.id);
        }
      }}
      className="docs-row-12 documents-page-e3" style={{ '--documents-page-background-color': selected ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : hover ? 'var(--surface-2)' : 'transparent' } as CSSProperties}>
      <td className="docs-td">
        <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: casilla de selección de la fila */ type="button" onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }} className={`docs-btn-4 document-sx16 ${selected ? 'document-sx12' : 'document-sx17'} documents-page-e4`} style={{ '--documents-page-border': `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
          {selected && <Check size={9} color="white" strokeWidth={3} />}
        </Pulsable>
      </td>
      <td className="docs-td-2">
        <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
      </td>
      <td className="docs-td-3">
        <div className="docs-box-8">{doc.title}</div>
        <ReservaChip reserva={doc.checkout} />
        {lv?.file_name && <div className="docs-box-9">{lv.file_name}</div>}
      </td>
      <td className="u-pad-10-12">
        <Chip text={etiquetaCategoria(t, doc.category)} color={catS.c} bg={catS.bg} />
      </td>
      <td className="u-pad-10-12">
        {doc.requires_approval ? <ChipAprobacion estado={doc.approval_status} /> : <span className="u-text3-xs">—</span>}
      </td>
      <td className="docs-td-4">
        {lv ? fmtBytes(lv.file_size) : '—'}
      </td>
      <td className="docs-td-5">{fmtDate(doc.created_at)}</td>
      <td className="docs-td-6">{doc.created_by_name || '—'}</td>
      <td className="docs-td-7" onClick={e => e.stopPropagation()}>
        <div className={`docs-row-13 ${hover ? 'document-sx14' : 'document-sx15'}`}>
          {lv?.download_url && (
            <a href={sanitizeUrl(lv.download_url)} target="_blank" rel="noreferrer" title={t('pagina_docs.descargar_documento')} aria-label={t('pagina_docs.descargar_documento')}
              className="docs-link-2">
              <Download size={11} />
            </a>
          )}
          <IconButton variante="caja" tono="acento" onClick={() => onSummary(doc.id)} title={t('pagina_docs.generar_resumen_ia')} ariaLabel={t('pagina_docs.generar_resumen_ia')}>
            <Sparkles size={11} />
          </IconButton>
          <IconButton variante="caja" tono="peligro" onClick={() => onDelete(doc)} title={t('pagina_docs.eliminar_documento')} ariaLabel={t('pagina_docs.eliminar_documento')}>
            <Trash2 size={11} />
          </IconButton>
        </div>
      </td>
    </tr>
  );
}
