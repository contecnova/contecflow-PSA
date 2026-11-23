/**
 * Utilidades, estilos, etiquetas y tipos compartidos de la gestión documental.
 * Troceado de DocumentsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { CSSProperties, ReactNode } from 'react'
import type {
  Documento,
  DocumentoEnLista,
  PermisoDeDocumento,
  ReservaDeDocumento,
  VersionDeDocumento,
} from '../../services/api/tipos-documentos'
import { useAppT } from '../../i18n/AppLangContext'
import { X, Check, Clock, type LucideIcon } from 'lucide-react'
import { localeActivo } from '../../utils/helpers'
import { px } from '../../utils/estilos'

// ── Utilidades ─────────────────────────────────────────
export function fmtBytes(b: number | null | undefined) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

/** Tiempo relativo en el idioma activo ("hace 5 min", "5 min ago", "5分钟前"). */
export function relTime(d: string | null | undefined) {
  if (!d) return '';
  const rtf = new Intl.RelativeTimeFormat(localeActivo(), { numeric: 'auto', style: 'short' });
  const m = Math.floor((Date.now() - new Date(d).getTime()) / 60000);
  if (m < 2) return rtf.format(0, 'second');
  if (m < 60) return rtf.format(-m, 'minute');
  const h = Math.floor(m / 60);
  if (h < 24) return rtf.format(-h, 'hour');
  const days = Math.floor(h / 24);
  if (days < 7) return rtf.format(-days, 'day');
  if (days < 30) return rtf.format(-Math.floor(days / 7), 'week');
  return rtf.format(-Math.floor(days / 30), 'month');
}

export const FILE_COLORS: Record<string, { c: string; bg: string; label: string }> = {
  pdf:          { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 9%, transparent)', label: 'PDF' },
  image:        { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 9%, transparent)', label: 'IMG' },
  spreadsheet:  { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 9%, transparent)', label: 'XLS' },
  word:         { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 9%, transparent)', label: 'DOC' },
  presentation: { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 9%, transparent)', label: 'PPT' },
  archive:      { c: 'var(--purple)', bg: 'color-mix(in srgb, var(--purple) 9%, transparent)', label: 'ZIP' },
  text:         { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)', label: 'TXT' },
  other:        { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)', label: 'FILE' },
};

export function detectFileType(mime: string | null | undefined, name: string | null | undefined) {
  const ext = (name || '').split('.').pop()?.toLowerCase();
  if (mime?.startsWith('image/')) return 'image';
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (mime?.includes('spreadsheet') || mime?.includes('excel') || ['xls','xlsx','csv'].includes(ext)) return 'spreadsheet';
  if (mime?.includes('word') || mime?.includes('document') || ['doc','docx'].includes(ext)) return 'word';
  if (mime?.includes('presentation') || mime?.includes('powerpoint') || ['ppt','pptx'].includes(ext)) return 'presentation';
  if (['zip','tar','gz','rar','7z'].includes(ext)) return 'archive';
  if (mime?.startsWith('text/') || ['txt','md'].includes(ext)) return 'text';
  return 'other';
}

export function FileIcon({ mime, name, size = 36 }: { mime?: string | null; name?: string | null; size?: number }) {
  const type = detectFileType(mime, name);
  const ft = FILE_COLORS[type];
  return (
    <div className="docs-row documents-page-e1" style={{ '--documents-page-width': px(size), '--documents-page-height': px(size), '--documents-page-border-radius': px(Math.round(size * 0.22)), '--documents-page-background-color': ft.bg, '--documents-page-font-size': px(Math.round(size * 0.23)), '--documents-page-color': ft.c } as CSSProperties}>
      {ft.label}
    </div>
  );
}

export const CAT_STYLE: Record<string, { c: string; bg: string }> = {
  contract:     { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 8%, transparent)' },
  deliverable:  { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 8%, transparent)' },
  proposal:     { c: 'var(--purple)', bg: 'color-mix(in srgb, var(--purple) 8%, transparent)' },
  sop:          { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 8%, transparent)' },
  legal:        { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 8%, transparent)' },
  requirements: { c: 'var(--chart-teal)', bg: 'color-mix(in srgb, var(--chart-teal) 8%, transparent)' },
  report:       { c: 'var(--orange)', bg: 'color-mix(in srgb, var(--orange) 8%, transparent)' },
  presentation: { c: 'var(--chart-pink)', bg: 'color-mix(in srgb, var(--chart-pink) 8%, transparent)' },
  meeting_notes:{ c: 'var(--sky-blue)', bg: 'color-mix(in srgb, var(--sky-blue) 8%, transparent)' },
  other:        { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 8%, transparent)' },
};

export const APPROVAL_STYLE: Record<string, { c: string; bg: string; Icon: LucideIcon; label: string }> = {
  approved: { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 8%, transparent)', Icon: Check, label: 'pagina_docs.aprobado' },
  rejected: { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 8%, transparent)', Icon: X, label: 'pagina_docs.rechazado_2' },
  pending:  { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 8%, transparent)', Icon: Clock, label: 'pagina_docs.pendiente' },
};

/** Clave de la etiqueta de cada categoría (el backend manda el código: `meeting_notes`…). */
const CAT_LABEL: Record<string, string> = {
  contract: 'pagina_docs.contrato',
  deliverable: 'pagina_docs.entregable',
  proposal: 'pagina_docs.propuesta',
  sop: 'pagina_docs.procedimiento_sop',
  legal: 'pagina_docs.legal',
  requirements: 'pagina_docs.requisitos',
  report: 'pagina_docs.cat_report',
  presentation: 'pagina_docs.cat_presentation',
  meeting_notes: 'documents.notas_de_reunion',
  other: 'pagina_docs.otro',
};

export const etiquetaCategoria = (t: (k: string) => string, c?: string | null) => (c && CAT_LABEL[c] ? t(CAT_LABEL[c]) : c || '—');

export function ChipAprobacion({ estado }: { estado?: string | null }) {
  const t = useAppT();
  const a = APPROVAL_STYLE[estado || 'pending'] || APPROVAL_STYLE.pending;
  return <Chip text={<><a.Icon size={10} aria-hidden /> {t(a.label)}</>} color={a.c} bg={a.bg} />;
}

export function Chip({ text, color, bg }: { text: ReactNode; color?: string; bg?: string }) {
  return (
    <span className="docs-row-2 documents-page-e2" style={{ '--documents-page-background-color': bg, '--documents-page-color': color } as CSSProperties}>
      {text}
    </span>
  );
}

// ── Doc Card (Grid) ─────────────────────────────────────────

export type Reserva = ReservaDeDocumento | undefined

export type DocVersion = VersionDeDocumento

export type DocListItem = DocumentoEnLista

export type DocDetail = Documento

export type DocPermission = PermisoDeDocumento

/** `DocumentPermissionCreate` (app/schemas/documents.py). */
export interface PermissionGrant {
  access_level: string
  expires_at?: string
  user_id?: string
  role?: string
  department?: string
}

export interface MetaForm {
  title: string
  description: string
  category: string
  requires_approval: boolean
}

export interface DocItemProps {
  doc: DocListItem
  onView: (id: string) => void
  onDelete: (doc: DocListItem) => void
  onSummary: (id: string) => void
  selected: boolean
  onToggleSelect: (id: string) => void
}
