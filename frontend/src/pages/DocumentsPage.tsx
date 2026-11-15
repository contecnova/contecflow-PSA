/**
 * DocumentsPage — Rediseño completo del hub de gestión documental
 * Diseo integrado con el sistema visual de Contecflow (surface vars, accent, etc.)
 * Funcionalidades: KPIs, grid/tabla, drawer de detalle, carga modal dos columnas,
 * acciones bulk, etiquetas, aprobaciones, historial de versiones, resmenes IA
 */
import { useAppLang } from '../i18n/AppLangContext'
import _React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import type { CSSProperties, ReactNode, DragEvent } from 'react';
import { useId } from 'react'
import type { AxiosError } from 'axios';
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api, { documentsApi, projectsApi, usersApi, esFichaCompleta, type ApiError, type PathId } from '../services/api';
import type { Documento, DocumentoEnLista, PermisoDeDocumento, ReservaDeDocumento, VersionDeDocumento } from '../services/api/tipos-documentos'
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import {
  Upload, Search, Grid3X3, List, Plus, Download, Trash2,
  Sparkles, History, X, Check, FolderOpen, Files, FileCheck,
  FileClock, FileMinus, TrendingUp, Eye, Info, Share2, Users,
  CheckCircle, XCircle, ExternalLink, Loader, Lock, LockOpen,
  type LucideIcon,
} from 'lucide-react';
import { Page, Button, Drawer, useDialogo } from '../components/ui'
import { alpha } from '../constants/theme'
import { localeActivo } from '../utils/helpers'
import DateInput from '../components/ui/DateInput'
import { STALE_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import { DOCUMENTS_LIST_LIMIT } from '../constants/pagination'
import './DocumentsPage.css'
import { px } from '../utils/estilos'

// ── Utilidades ─────────────────────────────────────────
function fmtBytes(b: number | null | undefined) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function fmtDate(d: string | null | undefined) {
  if (!d) return '';
  return new Date(d).toLocaleDateString(localeActivo(), { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Tiempo relativo en el idioma activo ("hace 5 min", "5 min ago", "5分钟前"). */
function relTime(d: string | null | undefined) {
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

const FILE_COLORS: Record<string, { c: string; bg: string; label: string }> = {
  pdf:          { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 9%, transparent)', label: 'PDF' },
  image:        { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 9%, transparent)', label: 'IMG' },
  spreadsheet:  { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 9%, transparent)', label: 'XLS' },
  word:         { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 9%, transparent)', label: 'DOC' },
  presentation: { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 9%, transparent)', label: 'PPT' },
  archive:      { c: 'var(--purple)', bg: 'color-mix(in srgb, var(--purple) 9%, transparent)', label: 'ZIP' },
  text:         { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)', label: 'TXT' },
  other:        { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)', label: 'FILE' },
};

function detectFileType(mime: string | null | undefined, name: string | null | undefined) {
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

function FileIcon({ mime, name, size = 36 }: { mime?: string | null; name?: string | null; size?: number }) {
  const type = detectFileType(mime, name);
  const ft = FILE_COLORS[type];
  return (
    <div className="docs-row documents-page-e1" style={{ '--documents-page-width': px(size), '--documents-page-height': px(size), '--documents-page-border-radius': px(Math.round(size * 0.22)), '--documents-page-background-color': ft.bg, '--documents-page-font-size': px(Math.round(size * 0.23)), '--documents-page-color': ft.c } as CSSProperties}>
      {ft.label}
    </div>
  );
}

const CAT_STYLE: Record<string, { c: string; bg: string }> = {
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

const APPROVAL_STYLE: Record<string, { c: string; bg: string; icon: string; label: string }> = {
  approved: { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 8%, transparent)', icon: '\u2713', label: 'pagina_docs.aprobado' },
  rejected: { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 8%, transparent)', icon: '\u2715', label: 'pagina_docs.rechazado_2' },
  pending:  { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 8%, transparent)', icon: '\u25f7', label: 'pagina_docs.pendiente' },
};

function Chip({ text, color, bg }: { text: ReactNode; color?: string; bg?: string }) {
  return (
    <span className="docs-row-2 documents-page-e2" style={{ '--documents-page-background-color': bg, '--documents-page-color': color } as CSSProperties}>
      {text}
    </span>
  );
}

// ── KPI card ─────────────────────────────────────────

function KpiCard({ icon: Icon, label, value, color, sub }: { icon: LucideIcon; label?: ReactNode; value?: ReactNode; color?: string; sub?: ReactNode }) {
  return (
    <div className="docs-row-3">
      <div className="docs-row-4 documents-page-e3" style={{ '--documents-page-background-color': alpha(color, '20') } as CSSProperties}>
        <Icon size={20} className="u-dato-color" style={{ '--dato-color': color } as CSSProperties} />
      </div>
      <div>
        <div className="docs-box">{value}</div>
        <div className="docs-box-2">{label}</div>
        {sub && <div className="docs-box-3">{sub}</div>}
      </div>
    </div>
  );
}

// ── Doc Card (Grid) ─────────────────────────────────────────

type Reserva = ReservaDeDocumento | undefined
type DocVersion = VersionDeDocumento
type DocListItem = DocumentoEnLista
type DocDetail = Documento
type DocPermission = PermisoDeDocumento

/** `DocumentPermissionCreate` (app/schemas/documents.py). */
interface PermissionGrant {
  access_level: string
  expires_at?: string
  user_id?: string
  role?: string
  department?: string
}

interface MetaForm {
  title: string
  description: string
  category: string
  requires_approval: boolean
}

interface DocItemProps {
  doc: DocListItem
  onView: (id: string) => void
  onDelete: (doc: DocListItem) => void
  onSummary: (id: string) => void
  selected: boolean
  onToggleSelect: (id: string) => void
}

/** Texto del `detail` de un error de FastAPI (cadena o lista de errores de validación). */
function detalleDeError(e: ApiError): string | undefined {
  const detail: unknown = e?.response?.data?.detail
  if (!detail) return undefined
  return Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg).join(' · ') : String(detail)
}

/** Quién tiene el documento reservado para editar (revisión 2026-11). */
function ReservaChip({ reserva }: { reserva: Reserva }) {
  const t = useAppT()
  const { user } = useAuth()
  if (!reserva) return null
  // Los listados mandan la reserva sin `mine` (reserva_de_documentos.vigente): se deduce.
  const mia = reserva.mine ?? reserva.user_id === user?.id
  return (
    <div title={reserva.expires_at ? t('documents.reserva_hasta', { fecha: new Date(reserva.expires_at).toLocaleString() }) : undefined}
      className={`docs-row-5 ${mia ? 'document-sx6' : 'document-sx7'}`}>
      <Lock size={10} /> {mia ? t('documents.reserva_tuya') : t('documents.reserva_de', { nombre: reserva.user_name || '—' })}
    </div>
  )
}

function DocCard({ doc, onView, onDelete, onSummary, selected, onToggleSelect }: DocItemProps) {
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
      <button
        type="button"
        onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }}
        className={`docs-btn document-sx11 ${selected ? 'document-sx12' : 'document-sx13'} ${selected || hover ? 'document-sx14' : 'document-sx15'} documents-page-e4`} style={{ '--documents-page-border': `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
        {selected && <Check size={9} color="white" strokeWidth={3} />}
      </button>

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
          <Chip text={doc.category} color={catS.c} bg={catS.bg} />
          {doc.requires_approval && (() => {
            const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
            return <Chip text={`${a.icon} ${t(a.label)}`} color={a.c} bg={a.bg} />;
          })()}
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
            <a href={lv.download_url} target="_blank" rel="noreferrer" title={t('pagina_docs.descargar_documento')}
              onClick={e => e.stopPropagation()}
              className="docs-link">
              <Download size={11} />
            </a>
          )}
          <button aria-label={t('pagina_docs.generar_resumen_ia')} onClick={(e) => { e.stopPropagation(); onSummary(doc.id); }} title={t('pagina_docs.generar_resumen_ia')}
            className="docs-btn-2">
            <Sparkles size={11} />
          </button>
          <button aria-label={t('pagina_docs.eliminar_documento')} onClick={(e) => { e.stopPropagation(); onDelete(doc); }} title={t('pagina_docs.eliminar_documento')}
            className="docs-btn-3">
            <Trash2 size={11} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Doc Row (Table) ─────────────────────────────────────────

function DocRow({ doc, onView, onDelete, onSummary, selected, onToggleSelect }: DocItemProps) {
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
        <button type="button" onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }} className={`docs-btn-4 document-sx16 ${selected ? 'document-sx12' : 'document-sx17'} documents-page-e4`} style={{ '--documents-page-border': `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
          {selected && <Check size={9} color="white" strokeWidth={3} />}
        </button>
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
        <Chip text={doc.category} color={catS.c} bg={catS.bg} />
      </td>
      <td className="u-pad-10-12">
        {doc.requires_approval ? (() => {
          const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
          return <Chip text={`${a.icon} ${t(a.label)}`} color={a.c} bg={a.bg} />;
        })() : <span className="u-text3-xs">—</span>}
      </td>
      <td className="docs-td-4">
        {lv ? fmtBytes(lv.file_size) : '—'}
      </td>
      <td className="docs-td-5">{fmtDate(doc.created_at)}</td>
      <td className="docs-td-6">{doc.created_by_name || '—'}</td>
      <td className="docs-td-7" onClick={e => e.stopPropagation()}>
        <div className={`docs-row-13 ${hover ? 'document-sx14' : 'document-sx15'}`}>
          {lv?.download_url && (
            <a href={lv.download_url} target="_blank" rel="noreferrer"
              className="docs-link-2">
              <Download size={11} />
            </a>
          )}
          <button onClick={() => onSummary(doc.id)}
            className="docs-btn-5">
            <Sparkles size={11} />
          </button>
          <button onClick={() => onDelete(doc)}
            className="docs-btn-6">
            <Trash2 size={11} />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Upload Modal ─────────────────────────────────────────

const CATS = ['contract','deliverable','proposal','sop','legal','requirements','report','presentation','meeting_notes','other'];

function UploadModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState({ title:'', description:'', category:'other', tags:'', requires_approval: false, project_id:'' });

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-minimal'],
    queryFn: () => projectsApi.list().then(r => r.data),
    staleTime: STALE_SHORT_MS,
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file!);
      fd.append('title', form.title || file!.name);
      if (form.description) fd.append('description', form.description);
      fd.append('category', form.category);
      if (form.tags) fd.append('tags', form.tags);
      fd.append('requires_approval', String(form.requires_approval));
      if (form.project_id) fd.append('project_id', form.project_id);
      return documentsApi.upload(fd);
    },
    onSuccess: () => { toast.success(t('pagina_docs.documento_subido_correctamente')); onSuccess(); },
    onError: (e: ApiError) => toast.error(detalleDeError(e) || t('pagina_docs.error_al_subir')),
  });

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); }
  }, []);

  const pickFile = (f: File) => { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); };
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose);

  if (!open) return null;

  const fileType = file ? detectFileType(undefined, file.name) : null;
  const fileFt = fileType ? FILE_COLORS[fileType] : null;

  return (
    <div role="presentation" className="docs-overlay" onMouseDown={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="upload-dialog-title" className="docs-dialog" onMouseDown={e => e.stopPropagation()}>

        {/* Header */}
        <div className="docs-row-15">
          <div>
            <div id="upload-dialog-title" className="docs-box-10">{t('pagina_docs.subir_documento')}</div>
            <div className="docs-box-11">{t('documents.arrastra_un_archivo_o_haz_clic_para')}</div>
          </div>
          <button onClick={onClose} className="docs-btn-7">
            <X size={18} />
          </button>
        </div>

        {/* Body: dos columnas */}
        <div className="docs-grid">
          {/* Izquierda: zona de carga */}
          <div className="docs-box-12">
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileRef.current?.click();
                }
              }}
              className={`docs-stack-3 document-sx8 ${dragOver ? 'document-sx18' : 'document-sx17'} documents-page-e4`} style={{ '--documents-page-border': `2px dashed ${dragOver ? 'var(--accent)' : file ? (fileFt?.c || 'var(--success)') : 'var(--surface-5)'}` } as CSSProperties}>
              <input ref={fileRef} type="file" aria-label={t('documents.clic_para_seleccionar_archivo')} className="docs-input" onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f); }} />
              {file ? (
                <>
                  <FileIcon mime={undefined} name={file.name} size={56} />
                  <div className="docs-box-13">{file.name}</div>
                  <div className="u-text3-mono-xs">{fmtBytes(file.size)}</div>
                  <button onClick={e => { e.stopPropagation(); setFile(null); }}
                    className="docs-btn-8">
                    {t('pagina_docs.cambiar_archivo')} 
                  </button>
                </>
              ) : (
                <>
                  <div className="docs-row-16">
                    <Upload size={22} className="u-text3" />
                  </div>
                  <div className="docs-box-14">{t('pagina_docs.arrastra_aqui_tu_archivo')}</div>
                  <div className="u-text3-xs">{t('documents.o_haz_clic_para_seleccionar')}</div>
                  <div className="docs-box-15">{t('documents.pdf_word_excel_imagenes_max_100_mb')}</div>
                </>
              )}
            </div>
          </div>

          {/* Derecha: metadatos */}
          <div className="docs-stack-4">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="documents-page-e7">{t('documents.titulo')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} className="documents-page-e8" placeholder={file?.name || t('pagina_docs.titulo_del_documento')} />
            </div>
            <div>
              <label className="documents-page-e7">{t('documents.descripcion')}</label>
              <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={2} className="documents-page-e5" placeholder={t('documents.descripcion_del_documento')} aria-label={t('documents.descripcion_del_documento')} />
            </div>
            <div className="u-grid2-10">
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="documents-page-e7">{t('documents.categoria')}</label>
                <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} className="documents-page-e8">
                  {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="documents-page-e7">{t('pagina_docs.proyecto')}</label>
                <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.project_id} onChange={e => setForm(p => ({ ...p, project_id: e.target.value }))} className="documents-page-e8">
                  <option value="">{t('documents.sin_proyecto')}</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} - ` : ''}{p.name}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label id={`${idCampo}-etiquetas-et`} htmlFor={`${idCampo}-etiquetas`} className="documents-page-e7">{t('pagina_docs.etiquetas')}</label>
              <input id={`${idCampo}-etiquetas`} aria-labelledby={`${idCampo}-etiquetas-et`} value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} className="documents-page-e8" placeholder={t('documents.etiquetas_separadas_por_comas')} aria-label={t('documents.etiquetas_separadas_por_comas')} />
            </div>
            <label className="docs-label-2">
              <input type="checkbox" aria-label={t('documents.requiere_aprobacion_antes_de_usar')} checked={form.requires_approval} onChange={e => setForm(p => ({ ...p, requires_approval: e.target.checked }))}
                className="docs-input-2" />
              <span className="u-text2-base">{t('documents.requiere_aprobacion_antes_de_usar')}</span>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className="docs-row-17">
          <button onClick={onClose} className="docs-btn-9">
            {t('pagina_docs.cancelar')}
          </button>
          <button onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
            className={`docs-btn-10 ${!file ? 'document-sx19' : 'document-sx20'}`}>
            {uploadMutation.isPending ? <><Loader size={14} className="docs-box-40" />{' '}{t('pagina_docs.subiendo')}</> : <><Upload size={14} />{' '}{t('pagina_docs.subir_documento')}</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Document Drawer (panel lateral) ─────────────────────────────────────────

// ── Share panel (per-document permissions) ────────────────────────────────────
const ROLES_AVAILABLE = ['admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor'];
const ACCESS_LEVELS = [
  { v: 'viewer', l: 'pagina_docs.lector_abrir_y_descargar' },
  { v: 'editor', l: 'pagina_docs.editor_subir_versiones' },
  { v: 'admin', l: 'pagina_docs.admin_gestionar_permisos' },
];

function SharePanel({ documentId }: { documentId: PathId }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast();
  const qc = useQueryClient();
  const [subjectType, setSubjectType] = useState('user'); // user | role | department
  const [userId, setUserId] = useState('');
  const [roleVal, setRoleVal] = useState('pm');
  const [deptVal, setDeptVal] = useState('');
  const [accessLevel, setAccessLevel] = useState('viewer');
  const [expiresAt, setExpiresAt] = useState('');

  const { data: perms = [] } = useQuery<DocPermission[]>({
    queryKey: ['document-permissions', documentId],
    queryFn: () => documentsApi.listPermissions(documentId).then(r => r.data),
  });

  const { data: users = [] } = useQuery({
    queryKey: ['users-min'],
    queryFn: () => usersApi.list().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  });

  const departments = useMemo(() => {
    const s = new Set<string>();
    users.forEach(u => { if (u.department) s.add(u.department); });
    return [...s].sort();
  }, [users]);

  const grantMutation = useMutation({
    mutationFn: (payload: PermissionGrant) => documentsApi.grantPermission(documentId, payload),
    onSuccess: () => {
      toast.success(t('pagina_docs.permiso_concedido'));
      qc.invalidateQueries({ queryKey: ['document-permissions', documentId] });
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setUserId(''); setDeptVal(''); setExpiresAt('');
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.no_se_pudo_conceder_el_permiso')),
  });

  const revokeMutation = useMutation({
    mutationFn: (permId: string) => documentsApi.revokePermission(documentId, permId),
    onSuccess: () => {
      toast.success(t('pagina_docs.permiso_revocado'));
      qc.invalidateQueries({ queryKey: ['document-permissions', documentId] });
      qc.invalidateQueries({ queryKey: ['document', documentId] });
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.no_se_pudo_revocar')),
  });

  const submitGrant = () => {
    const payload: PermissionGrant = { access_level: accessLevel };
    if (expiresAt) payload.expires_at = new Date(expiresAt).toISOString();
    if (subjectType === 'user') {
      if (!userId) { toast.error(t('pagina_docs.selecciona_un_usuario')); return; }
      payload.user_id = userId;
    } else if (subjectType === 'role') {
      payload.role = roleVal;
    } else if (subjectType === 'department') {
      const d = (deptVal || '').trim();
      if (!d) { toast.error(t('pagina_docs.indica_un_departamento')); return; }
      payload.department = d;
    }
    grantMutation.mutate(payload);
  };

  const subjectLabel = (p: DocPermission) => {
    if (p.user_id) return `👤 ${p.user_name || p.user_id}`;
    if (p.role) return t('pagina_docs.rol', { role: p.role });
    if (p.department) return t('pagina_docs.departamento', { department: p.department });
    return '—';
  };


  return (
    <div className="docs-stack-5">
      <div className="docs-card-2">
        <strong>{t('documents.por_defecto')}</strong>{t('documents.el_creador_del_documento_y_los_miembros')}
      </div>

      {/* Add grant */}
      <div className="docs-card-3">
        <div className="docs-row-18">
          <Share2 size={14} />{' '}{t('pagina_docs.conceder_acceso')}
        </div>

        <div className="docs-grid-2">
          {[
            { v: 'user', l: t('pagina_docs.usuario'), icon: Users },
            { v: 'role', l: t('pagina_docs.rol_2') },
            { v: 'department', l: t('pagina_docs.departamento_2') },
          ].map(opt => (
            <button key={opt.v} onClick={() => setSubjectType(opt.v)}
              className={`docs-btn-11 document-sx21 ${subjectType === opt.v ? 'document-sx22' : 'document-sx23'} documents-page-e4`} style={{ '--documents-page-border': `1px solid ${subjectType === opt.v ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
              {opt.l}
            </button>
          ))}
        </div>

        {subjectType === 'user' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="documents-page-e9">{t('pagina_docs.usuario')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={userId} onChange={e => setUserId(e.target.value)} className="documents-page-e10">
              <option value="">{t('documents.selecciona_un_usuario')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{esFichaCompleta(u) ? ` (${u.email})` : ''}</option>)}
            </select>
          </div>
        )}
        {subjectType === 'role' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="documents-page-e9">{t('pagina_docs.rol_2')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={roleVal} onChange={e => setRoleVal(e.target.value)} className="documents-page-e10">
              {ROLES_AVAILABLE.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        )}
        {subjectType === 'department' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="documents-page-e9">{t('pagina_docs.departamento_2')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="text" value={deptVal} onChange={e => setDeptVal(e.target.value)}
              list="departments-list" placeholder={t('pagina_docs.ej_finance')}
              className="documents-page-e10" />
            <datalist id="departments-list">
              {departments.map(d => <option key={d} value={d} aria-label={d} />)}
            </datalist>
          </div>
        )}

        <div className="docs-grid-3">
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="documents-page-e9">{t('documents.nivel_de_acceso')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={accessLevel} onChange={e => setAccessLevel(e.target.value)} className="documents-page-e10">
              {ACCESS_LEVELS.map(a => <option key={a.v} value={a.v}>{t(a.l)}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="documents-page-e9">{t('pagina_docs.caducidad_opcional')}</label>
            <DateInput id={`${idCampo}-5`} withTime value={expiresAt} onChange={e => setExpiresAt(e.target.value)} className="documents-page-e10" />
          </div>
        </div>

        <button onClick={submitGrant} disabled={grantMutation.isPending}
          className="docs-btn-12">
          <Check size={13} /> {grantMutation.isPending ? t('pagina_docs.concediendo') : t('pagina_docs.conceder_acceso')}
        </button>
      </div>

      {/* Existing grants */}
      <div>
        <div className="docs-box-16">
          {t('pagina_docs.permisos_actuales')}{' '}<span className="docs-label-3">({perms.length})</span>
        </div>
        {perms.length === 0 ? (
          <div className="docs-card-4">
            {t('documents.sin_permisos_explicitos_solo_el_creador_y')}
          </div>
        ) : (
          <div className="u-stack-6">
            {perms.map(p => (
              <div key={p.id} className="docs-row-19">
                <div className="u-flex1-min0">
                  <div className="u-text1-sm-600">{subjectLabel(p)}</div>
                  <div className="u-text3-2xs">
                    {ACCESS_LEVELS.find(a => a.v === p.access_level)?.l ? t(ACCESS_LEVELS.find(a => a.v === p.access_level)!.l) : p.access_level}
                    {p.granted_by_name && t('pagina_docs.concedido_por', { granted_by_name: p.granted_by_name })}
                    {p.expires_at && t('pagina_docs.caduca', { v1: new Date(p.expires_at).toLocaleDateString(localeActivo()) })}
                  </div>
                </div>
                <button onClick={() => revokeMutation.mutate(p.id)} disabled={revokeMutation.isPending}
                  className="docs-btn-13">
                  <Trash2 size={11} />{' '}{t('pagina_docs.revocar')}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DocumentDrawer({ documentId, onClose, onRefresh }: { documentId: string; onClose: () => void; onRefresh: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [tab, setTab] = useState('preview');  // preview | versions | meta
  const [file, setFile] = useState<File | null>(null);
  const [changeNote, setChangeNote] = useState('');
  const [showUploadVersion, setShowUploadVersion] = useState(false);
  const [previewVersion, setPreviewVersion] = useState<DocVersion | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [isEditingMeta, setIsEditingMeta] = useState(false);
  const [metaForm, setMetaForm] = useState<MetaForm | null>(null);

  const { data: doc, isLoading } = useQuery<DocDetail>({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const res = await documentsApi.get(documentId);
      const d: DocDetail = res.data;
      if (d.versions) d.versions = d.versions.map(v => ({ ...v, download_url: v.download_url || v.s3_url }));
      return d;
    },
  });

  useEffect(() => {
    if (doc?.versions?.length && !previewVersion) setPreviewVersion(doc.versions[0]);
    // `previewVersion` faltaba (auditoría 2026-08, P1-6). El guard `!previewVersion`
    // impide reescribirlo, así que incluirlo es seguro y hace que el efecto
    // reaccione si la vista previa se limpia.
  }, [doc, previewVersion]);

  const approveMutation = useMutation({
    mutationFn: ({ status, note }: { status: string; note?: string }) => documentsApi.approve(documentId, { status, note }),
    onSuccess: (_: unknown, { status }: { status: string }) => { toast.success(status === 'approved' ? t('pagina_docs.paso_aprobado') : t('pagina_docs.documento_rechazado')); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.error')),
  });

  const submitApprovalMutation = useMutation({
    mutationFn: () => documentsApi.submitApproval(documentId),
    onSuccess: () => { toast.success(t('pagina_docs.solicitud_de_aprobacion_enviada')); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.no_hay_ningun_flujo_de_aprobacion')),
  });

  const summaryMutation = useMutation({
    mutationFn: () => documentsApi.aiSummary(documentId),
    onSuccess: () => {
      toast.success(t('pagina_docs.resumen_ia_generado'));
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setTab('meta');
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.error_ia')),
  });

  const reserva: Reserva = doc?.checkout
  const deOtro = !!reserva && !reserva.mine
  const reservaMutation = useMutation({
    mutationFn: (accion: 'checkout' | 'checkin' | 'force') =>
      accion === 'checkout' ? documentsApi.checkout(documentId) : documentsApi.checkin(documentId, accion === 'force'),
    onSuccess: (_: unknown, accion: 'checkout' | 'checkin' | 'force') => {
      toast.success(t(accion === 'checkout' ? 'documents.reserva_hecha' : 'documents.reserva_liberada'))
      qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh()
    },
    // El 409 de la reserva trae `detail` como objeto `{ message, ... }`.
    onError: (e: AxiosError<{ detail?: string | { message?: string } }>) => {
      const d = e?.response?.data?.detail
      toast.error(typeof d === 'string' ? d : d?.message || t('pagina_docs.error'))
    },
  });

  const versionMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file!);
      if (changeNote) fd.append('change_note', changeNote);
      return documentsApi.addVersion(documentId, fd);
    },
    onSuccess: () => { toast.success(t('pagina_docs.nueva_version_subida')); qc.invalidateQueries({ queryKey: ['document', documentId] }); setFile(null); setChangeNote(''); setShowUploadVersion(false); onRefresh(); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.error')),
  });

  const updateMetaMutation = useMutation({
    mutationFn: (data: MetaForm) => documentsApi.update(documentId, data),
    onSuccess: () => {
      toast.success(t('pagina_docs.metadatos_actualizados'));
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      qc.invalidateQueries({ queryKey: ['documents'] });
      setIsEditingMeta(false);
      onRefresh();
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.error_al_guardar')),
  });

  const activeVer = previewVersion || doc?.versions?.[0] || null;
  const catS = doc ? (CAT_STYLE[doc.category] || CAT_STYLE.other) : null;

  useEffect(() => {
    if (!activeVer?.download_url) return;
    setPreviewError(false);
    // Only validate local API file URLs (S3 presigned URLs embed auth in query params)
    if (!activeVer.download_url.startsWith('/api/')) return;
    const fileType = detectFileType(activeVer.file_mime_type, activeVer.file_name);
    if (fileType !== 'pdf' && fileType !== 'image') return;
    // Por el cliente (refresco de sesión). La URL ya trae el prefijo de la API:
    // `baseURL: ''` evita que axios se lo añada otra vez.
    api.head(activeVer.download_url, { baseURL: '' })
      .catch(() => setPreviewError(true));
    // Faltaban file_mime_type y file_name (auditoría 2026-08, P1-6): el efecto
    // los usa para decidir el tipo, así que si cambiaban sin cambiar la URL la
    // comprobación se hacía con valores obsoletos.
  }, [activeVer?.download_url, activeVer?.file_mime_type, activeVer?.file_name]);

  return (
    <Drawer onClose={onClose} ariaLabel={doc?.title || t('pagina_docs.documento')} width={600} zIndex={900}>
        {isLoading ? (
          <div className="docs-row-20">
            <Loader size={18} className="docs-box-41" />{' '}{t('pagina_docs.cargando')}
          </div>
        ) : !doc ? (
          <div className="docs-row-21">{t('documents.documento_no_encontrado')}</div>
        ) : (
          <>
            {/* Drawer header */}
            <div className="docs-box-17">
              <div className="docs-row-22">
                <div className="u-flex1-min0">
                  <div className="docs-row-23">
                    <FileIcon mime={activeVer?.file_mime_type} name={activeVer?.file_name} size={38} />
                    <div className="u-flex1-min0">
                      <h2 className="docs-title">{doc.title}</h2>
                      {doc.description && <p className="docs-text">{doc.description}</p>}
                    </div>
                  </div>
                  <div className="docs-row-24">
                    <Chip text={doc.category} color={catS!.c} bg={catS!.bg} />
                    {doc.requires_approval && (() => {
                      const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
                      return <Chip text={`${a.icon} ${t(a.label)}`} color={a.c} bg={a.bg} />;
                    })()}
                    {doc.tags?.map(t => (
                      <span key={t} className="docs-label-4">#{t}</span>
                    ))}
                  </div>
                </div>
                <button onClick={onClose} aria-label={t('pagina_docs.cerrar')} className="docs-btn-14">
                  <X size={18} />
                </button>
              </div>

              {/* Action row */}
              <div className="u-wrap-8">
                {doc.requires_approval && doc.approval_status === 'pending' && !doc.approval_request && (
                  <button
                    onClick={() => submitApprovalMutation.mutate()}
                    disabled={submitApprovalMutation.isPending}
                    className="docs-btn-15"
                  >
                    <FileClock size={13} /> {submitApprovalMutation.isPending ? t('pagina_docs.enviando') : t('pagina_docs.enviar_para_aprobacion')}
                  </button>
                )}
                {doc.requires_approval && doc.approval_status === 'rejected' && (
                  <button
                    onClick={() => submitApprovalMutation.mutate()}
                    disabled={submitApprovalMutation.isPending}
                    title={t('documents.reabre_un_nuevo_flujo_de_aprobacion_el')}
                    className="docs-btn-15"
                  >
                    <FileClock size={13} /> {submitApprovalMutation.isPending ? t('pagina_docs.reenviando') : t('pagina_docs.reenviar_a_aprobacion')}
                  </button>
                )}
                {doc.requires_approval && doc.approval_status === 'pending' && doc.approval_request?.status === 'pending' && (
                  <>
                    <button onClick={() => approveMutation.mutate({ status: 'approved' })} disabled={approveMutation.isPending} className="docs-btn-16">
                      <CheckCircle size={13} />{' '}{t('pagina_docs.aprobar_paso')}
                    </button>
                    <button onClick={() => approveMutation.mutate({ status: 'rejected' })} disabled={approveMutation.isPending} className="docs-btn-17">
                      <XCircle size={13} />{' '}{t('pagina_docs.rechazar')}
                    </button>
                  </>
                )}
                {!reserva && (
                  <button onClick={() => reservaMutation.mutate('checkout')} disabled={reservaMutation.isPending}
                    title={t('documents.reserva_ayuda')}
                    className="docs-btn-18">
                    <Lock size={13} /> {t('documents.reservar')}
                  </button>
                )}
                {reserva?.mine && (
                  <button onClick={() => reservaMutation.mutate('checkin')} disabled={reservaMutation.isPending}
                    className="docs-btn-19">
                    <LockOpen size={13} /> {t('documents.liberar')}
                  </button>
                )}
                <button onClick={() => summaryMutation.mutate()} disabled={summaryMutation.isPending}
                  className="docs-btn-20">
                   <Sparkles size={13} /> {summaryMutation.isPending ? t('pagina_docs.generando') : t('pagina_docs.resumen_ia')}
                </button>
                {activeVer?.download_url && (
                  <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                    className="docs-link-3">
                    <Download size={13} />{' '}{t('pagina_docs.descargar')}
                  </a>
                )}
              </div>
            </div>

            {deOtro && (
              <div role="status" className="docs-row-25">
                <Lock size={14} color="var(--warning)" />
                <span className="u-flex1">
                  {t('documents.reserva_aviso', { nombre: reserva?.user_name || '—', fecha: reserva?.expires_at ? new Date(reserva.expires_at).toLocaleString() : '—' })}
                </span>
                <button onClick={() => reservaMutation.mutate('force')} disabled={reservaMutation.isPending}
                  className="docs-btn-21">
                  {t('documents.reserva_forzar')}
                </button>
              </div>
            )}

            {/* Tabs */}
            <div className="docs-row-26">
              <button className={`docs-tab-btn ${tab === 'preview' ? 'docs-tab-btn--activo' : ''}`} onClick={() => setTab('preview')}>
                <Eye size={12} className="docs-box-42" />{' '}{t('pagina_docs.vista_previa')}
              </button>
              <button className={`docs-tab-btn ${tab === 'versions' ? 'docs-tab-btn--activo' : ''}`} onClick={() => setTab('versions')}>
                <History size={12} className="docs-box-42" />
                {t('pagina_docs.versiones')}{' '}{(doc.versions?.length ?? 0) > 0 && `(${doc.versions.length})`}
              </button>
              <button className={`docs-tab-btn ${tab === 'meta' ? 'docs-tab-btn--activo' : ''}`} onClick={() => setTab('meta')}>
                <Info size={12} className="docs-box-42" />{' '}{t('pagina_docs.metadatos')}
              </button>
              <button className={`docs-tab-btn ${tab === 'share' ? 'docs-tab-btn--activo' : ''}`} onClick={() => setTab('share')}>
                <Share2 size={12} className="docs-box-42" />{' '}{t('pagina_docs.compartir')}
              </button>
            </div>

            {/* Tab content */}
            <div className="docs-box-18">

              {/* Preview */}
              {tab === 'preview' && activeVer?.download_url && (
                <div className="docs-card-5">
                  <div className="docs-row-27">
                    <span className="u-text3-xs">{activeVer.file_name} · {fmtBytes(activeVer.file_size)}</span>
                    <a href={activeVer.download_url} target="_blank" rel="noreferrer" className="docs-link-4">
                       <ExternalLink size={11} /> {t('documents.abrir_en_nueva_pestana')}
                    </a>
                  </div>
                  {(() => {
                    if (previewError) return (
                      <div className="docs-box-19">
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div className="docs-box-20">{t('documents.el_archivo_no_esta_disponible_en_el')}</div>
                        {activeVer.download_url && (
                          <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                            className="docs-link-5">
                            <Download size={14} />{' '}{t('pagina_docs.intentar_descargar')}
                          </a>
                        )}
                      </div>
                    );
                    const type = detectFileType(activeVer.file_mime_type, activeVer.file_name);
                    if (type === 'pdf') return <iframe src={activeVer.download_url} className="docs-box-21" title={t('documents.vista_previa_del_pdf')} onError={() => setPreviewError(true)} />;
                    if (type === 'image') return <img src={activeVer.download_url} alt={activeVer.file_name} loading="lazy" decoding="async" className="docs-box-22" onError={() => setPreviewError(true)} />;
                    return (
                      <div className="docs-box-19">
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div className="docs-box-20">{t('documents.vista_previa_no_disponible_para_este_tipo')}</div>
                        <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                          className="docs-link-5">
                          <Download size={14} /> {t('documents.descargar_para_ver')}
                        </a>
                      </div>
                    );
                  })()}
                </div>
              )}
              {tab === 'preview' && !activeVer?.download_url && (
                <div className="docs-box-23">
                  <FolderOpen size={36} className="docs-box-43" />
                  {t('documents.este_documento_no_tiene_archivo_adjunto_todavia')}
                </div>
              )}

              {/* Versions */}
              {tab === 'versions' && (
                <div>
                  <div className="docs-stack-6">
                    {(doc.versions || []).map((v, i) => (
                      <div key={v.id}
                        onClick={() => { setPreviewVersion(v); setTab('preview'); }}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setPreviewVersion(v);
                            setTab('preview');
                          }
                        }}
                        className={`docs-row-28 document-sx24 ${activeVer?.id === v.id ? 'document-sx25' : 'document-sx18'} documents-page-e4`} style={{ '--documents-page-border': `1px solid ${activeVer?.id === v.id ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        <div className={`docs-row-29 ${activeVer?.id === v.id ? 'document-sx26' : 'document-sx27'}`}>
                          v{v.version_num}
                        </div>
                        <div className="u-flex1-min0">
                          <div className="docs-box-8">{v.file_name}</div>
                          {v.change_note && <div className="docs-box-24">{v.change_note}</div>}
                          <div className="u-text3-2xs">{v.uploader_name} · {fmtDate(v.created_at)} · {fmtBytes(v.file_size)}</div>
                        </div>
                        {i === 0 && <span className="docs-label-5">{t('pagina_docs.actual')}</span>}
                        {v.download_url && (
                          <a href={v.download_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                            className="docs-link-6">
                            <Download size={12} />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Upload new version */}
                  {!showUploadVersion ? (
                    <button onClick={() => setShowUploadVersion(true)} disabled={deOtro}
                      title={deOtro ? t('documents.reserva_de', { nombre: reserva?.user_name || '—' }) : undefined}
                      className={`docs-btn-22 ${deOtro ? 'document-sx28' : 'document-sx29'}`}>
                      <Upload size={14} /> {t('documents.subir_nueva_version')}
                    </button>
                  ) : (
                    <div className="docs-stack-7">
                      <div onClick={() => fileRef.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileRef.current?.click(); } }} className="docs-box-25 document-sx21 documents-page-e4" style={{ '--documents-page-border': `2px dashed ${file ? 'var(--success)' : 'var(--surface-5)'}` } as CSSProperties}>
                        {file ? <span className="u-text1-base-600">{file.name}</span>
                          : <span className="u-text3-sm"><Upload size={13} className="docs-box-42" />{t('documents.clic_para_seleccionar_archivo')}</span>}
                        <input ref={fileRef} type="file" aria-label={t('documents.clic_para_seleccionar_archivo')} className="docs-input" onChange={e => setFile(e.target.files?.[0] ?? null)} />
                      </div>
                      <input placeholder={t('documents.nota_del_cambio')} value={changeNote} onChange={e => setChangeNote(e.target.value)} className="documents-page-e8" aria-label={t('documents.nota_del_cambio')} />
                      <div className="u-row-8">
                        <button onClick={() => versionMutation.mutate()} disabled={!file || versionMutation.isPending}
                          className={`docs-btn-23 ${!file ? 'document-sx19' : 'document-sx20'}`}>
                          {versionMutation.isPending ? t('pagina_docs.subiendo') : t('pagina_docs.subir')}
                        </button>
                        <button onClick={() => { setShowUploadVersion(false); setFile(null); setChangeNote(''); }}
                          className="docs-btn-24">
                          {t('pagina_docs.cancelar')}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Metadata */}
              {tab === 'meta' && !isEditingMeta && (
                <div>
                  {/* AI Summary card */}
                  {doc.ai_summary && (
                    <div className="docs-card-6">
                      <div className="docs-row-30">
                        <Sparkles size={12} />{' '}{t('pagina_docs.resumen_ia')}
                      </div>
                      <div className="docs-box-26">{doc.ai_summary}</div>
                    </div>
                  )}
                  <div className="docs-grid-4">
                    {([
                      [t('pagina_docs.creado_por'), doc.created_by_name || '—'],
                      [t('pagina_docs.fecha_creacion'), fmtDate(doc.created_at)],
                      [t('pagina_docs.categoria'), doc.category],
                      [t('pagina_docs.versiones'), doc.versions?.length || 1],
                      [t('pagina_docs.requiere_aprob'), doc.requires_approval ? t('pagina_docs.si') : t('pagina_docs.no')],
                      [t('pagina_docs.estado_aprob'), doc.approval_status || '—'],
                      doc.approved_by_name && [t('pagina_docs.aprobado_por'), doc.approved_by_name],
                      doc.approved_at && [t('pagina_docs.fecha_aprob'), fmtDate(doc.approved_at)],
                    ] as Array<[string, ReactNode] | null | undefined | ''>).filter((x): x is [string, ReactNode] => Boolean(x)).map(([k, v]) => (
                      <div key={k} className="docs-card-7">
                        <div className="docs-box-27">{k}</div>
                        <div className="u-text1-base-600">{v}</div>
                      </div>
                    ))}
                    {doc.description && (
                      <div className="docs-card-8">
                        <div className="docs-box-27">{t('documents.descripcion')}</div>
                        <div className="docs-box-28">{doc.description}</div>
                      </div>
                    )}
                    {(doc.tags?.length ?? 0) > 0 && (
                      <div className="docs-card-8">
                        <div className="docs-box-29">{t('pagina_docs.etiquetas')}</div>
                        <div className="docs-row-7">
                          {doc.tags.map(t => (
                            <span key={t} className="docs-label-6">#{t}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <button onClick={() => {
                    setMetaForm({ title: doc.title || '', description: doc.description || '', category: doc.category || 'other', requires_approval: doc.requires_approval ?? false });
                    setIsEditingMeta(true);
                  }} className="docs-btn-25">
                    {t('pagina_docs.editar_metadatos')}
                  </button>
                </div>
              )}
                    {/* Approval workflow panel */}
                    {doc.approval_request && (
                      <div className="docs-card-9">
                        <div className="docs-row-31">
                          <FileClock size={14} className="u-warning" />
                          {t('documents.flujo_de_aprobacion')} {doc.approval_request.workflow_name}
                        </div>
                        {/* Step indicator */}
                        <div className="docs-row-32">
                          {Array.from({ length: doc.approval_request.total_steps || 1 }, (_: unknown, i: number) => {
                            const stepNum = i + 1;
                            const isDone = stepNum < (doc.approval_request.current_step || 1);
                            const isCurrent = stepNum === (doc.approval_request.current_step || 1) && doc.approval_request.status === 'pending';
                            const isRejected = doc.approval_request.status === 'rejected';
                            const color = isDone ? 'var(--success)' : isCurrent ? 'var(--warning)' : isRejected && stepNum === doc.approval_request.current_step ? 'var(--danger)' : 'var(--surface-4)';
                            return (
                              <div key={stepNum} className="docs-row-33">
                                <div className={`docs-row-34 ${(isDone || isCurrent) ? 'document-sx30' : 'document-sx31'} documents-page-e3`} style={{ '--documents-page-background-color': color } as CSSProperties}>
                                  {isDone ? '✓' : stepNum}
                                </div>
                                {stepNum < (doc.approval_request.total_steps || 1) && (
                                  <div className={`docs-box-30 ${isDone ? 'document-sx32' : 'document-sx33'}`} />
                                )}
                              </div>
                            );
                          })}
                          <span className="docs-label-7">
                            {t('pagina_docs.paso_x_de_y', { actual: doc.approval_request.current_step, total: doc.approval_request.total_steps })}
                          </span>
                        </div>
                        {/* Current step info */}
                        {doc.approval_request.status === 'pending' && doc.approval_request.current_step_name && (
                          <div className="docs-box-31">
                            <span className="docs-label-8">{doc.approval_request.current_step_name}</span>
                            {doc.approval_request.current_approver_name && (
                              <> {t('documents.pendiente_de')} <span className="u-accent">{doc.approval_request.current_approver_name}</span></>
                            )}
                            {!doc.approval_request.current_approver_name && doc.approval_request.current_approver_role && (
                              <> {t('documents.pendiente_de_rol')} <span className="u-accent">{doc.approval_request.current_approver_role}</span></>
                            )}
                          </div>
                        )}
                        {doc.approval_request.status === 'approved' && (
                          <div className="docs-box-32">{t('pagina_docs.aprobado_completamente')}</div>
                        )}
                        {doc.approval_request.status === 'rejected' && (
                          <div className="docs-box-33">{t('pagina_docs.rechazado')}</div>
                        )}
                        {/* Decisions trail */}
                        {(doc.approval_request.decisions?.length ?? 0) > 0 && (
                          <div className="docs-box-34">
                            <div className="docs-box-29">{t('documents.historial_de_decisiones')}</div>
                            {doc.approval_request.decisions.map((d, idx) => (
                              <div key={idx} className="docs-row-35">
                                <div className={`docs-row-36 ${d.decision === 'approved' ? 'document-sx34' : 'document-sx35'}`}>
                                  <span className={`docs-label-9 ${d.decision === 'approved' ? 'document-sx36' : 'document-sx37'}`}>{d.decision === 'approved' ? '✓' : '✗'}</span>
                                </div>
                                <div>
                                  <span className="docs-label-10">{d.approver_name || t('pagina_docs.desconocido')}</span>
                                  <span className="docs-label-11">{t('pagina_docs.paso')}{' '}{d.step_order} · {d.decided_at ? new Date(d.decided_at).toLocaleDateString(localeActivo()) : ''}</span>
                                  {d.note && <div className="docs-box-35">"{d.note}"</div>}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
              {tab === 'meta' && isEditingMeta && metaForm && (
                <div className="u-stack-14">
                  <div>
                    <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="docs-label-12">{t('documents.titulo')}</label>
                    <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={metaForm.title} onChange={e => setMetaForm(f => f && ({ ...f, title: e.target.value }))} className="documents-page-e8" />
                  </div>
                  <div>
                    <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="docs-label-12">{t('documents.descripcion')}</label>
                    <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={metaForm.description} onChange={e => setMetaForm(f => f && ({ ...f, description: e.target.value }))} rows={3} className="documents-page-e6" />
                  </div>
                  <div>
                    <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="docs-label-12">{t('documents.categoria')}</label>
                    <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={metaForm.category} onChange={e => setMetaForm(f => f && ({ ...f, category: e.target.value }))} className="documents-page-e8">
                      <option value="contract">{t('pagina_docs.contrato')}</option>
                      <option value="deliverable">{t('pagina_docs.entregable')}</option>
                      <option value="proposal">{t('pagina_docs.propuesta')}</option>
                      <option value="sop">{t('pagina_docs.procedimiento_sop')}</option>
                      <option value="requirements">{t('pagina_docs.requisitos')}</option>
                      <option value="meeting_notes">{t('documents.notas_de_reunion')}</option>
                      <option value="legal">{t('pagina_docs.legal')}</option>
                      <option value="other">{t('pagina_docs.otro')}</option>
                    </select>
                  </div>
                  <div className="u-row-center-10">
                    <input type="checkbox" id="meta-req-approval" aria-labelledby="meta-req-approval-et" checked={metaForm.requires_approval} onChange={e => setMetaForm(f => f && ({ ...f, requires_approval: e.target.checked }))} className="docs-input-3" />
                    <label id="meta-req-approval-et" htmlFor="meta-req-approval" className="docs-label-13">{t('documents.requiere_aprobacion')}</label>
                  </div>
                  <div className="docs-row-37">
                    <button onClick={() => setIsEditingMeta(false)} className="docs-btn-26">{t('pagina_docs.cancelar')}</button>
                    <button onClick={() => updateMetaMutation.mutate(metaForm)} disabled={updateMetaMutation.isPending || !metaForm.title}
                      className="docs-btn-27">
                      {updateMetaMutation.isPending ? t('pagina_docs.guardando') : t('pagina_docs.guardar')}
                    </button>
                  </div>
                </div>
              )}

              {/* Share */}
              {tab === 'share' && <SharePanel documentId={documentId} />}
            </div>
          </>
        )}
    </Drawer>
  );
}

// ── Página principal ────────────────────────────────────────────

const SORT_OPTS = [
  { v: 'date_desc', l: 'pagina_docs.mas_recientes' },
  { v: 'date_asc',  l: 'pagina_docs.mas_antiguos' },
  { v: 'name_asc',  l: 'pagina_docs.a_z' },
  { v: 'size_desc', l: 'pagina_docs.mas_grandes' },
];

export default function DocumentsPage(): JSX.Element {
  const t = useAppT()
  const _t = useAppT()
  const toast = useToast();
  const qc = useQueryClient();
  const [viewMode, setViewMode] = useState('grid');
  const [search, setSearch] = useState('');
  const [filterCat, setFilterCat] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [sortBy, setSortBy] = useState('date_desc');
  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [drawerDocId, setDrawerDocId] = useState<string | null>(null);

  const { data: docsRaw = [], isLoading } = useQuery<DocListItem[]>({
    queryKey: ['documents', filterCat, filterStatus, search],
    queryFn: () => {
      // `page_size` (el backend no lee `limit`: con él llegaban solo los 50 primeros).
      const p: { page_size: number; category?: string; search?: string } = { page_size: DOCUMENTS_LIST_LIMIT };
      if (filterCat) p.category = filterCat;
      if (search) p.search = search;
      return documentsApi.list(p).then(r => r.data);
    },
  });

  const docs = useMemo(() => {
    let d = [...docsRaw];
    if (filterStatus === 'pending') d = d.filter(x => x.requires_approval && (x.approval_status === 'pending' || !x.approval_status));
    else if (filterStatus === 'approved') d = d.filter(x => x.requires_approval && x.approval_status === 'approved');
    else if (filterStatus === 'rejected') d = d.filter(x => x.requires_approval && x.approval_status === 'rejected');
    else if (filterStatus === 'no_approval') d = d.filter(x => !x.requires_approval);
    if (activeTags.length) d = d.filter(x => activeTags.every((t: string) => x.tags?.includes(t)));
    if (sortBy === 'date_desc') d.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    else if (sortBy === 'date_asc') d.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    else if (sortBy === 'name_asc') d.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    else if (sortBy === 'size_desc') d.sort((a, b) => (b.latest_version?.file_size || 0) - (a.latest_version?.file_size || 0));
    return d;
  }, [docsRaw, filterStatus, activeTags, sortBy]);

  const stats = useMemo(() => {
    const weekAgo = Date.now() - 7 * 86400000;
    return {
      total: docsRaw.length,
      pending: docsRaw.filter(d => d.requires_approval && (d.approval_status === 'pending' || !d.approval_status)).length,
      approved: docsRaw.filter(d => d.requires_approval && d.approval_status === 'approved').length,
      rejected: docsRaw.filter(d => d.requires_approval && d.approval_status === 'rejected').length,
      noApproval: docsRaw.filter(d => !d.requires_approval).length,
      thisWeek: docsRaw.filter(d => new Date(d.created_at).getTime() > weekAgo).length,
    };
  }, [docsRaw]);

  const allTags = useMemo(() => {
    const s = new Set<string>();
    docsRaw.forEach(d => d.tags?.forEach((t: string) => s.add(t)));
    return [...s].slice(0, 24);
  }, [docsRaw]);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => { toast.success(t('pagina_docs.documento_eliminado')); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => toast.error(t('pagina_docs.error_al_eliminar')),
  });

  const summaryMutation = useMutation({
    mutationFn: (id: string) => documentsApi.aiSummary(id),
    onSuccess: () => { toast.success(t('pagina_docs.resumen_ia_generado')); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('pagina_docs.error_ia')),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: () => Promise.all([...selectedIds].map(id => documentsApi.delete(id))),
    onSuccess: () => { toast.success(t('pagina_docs.documento_s_eliminados', { size: selectedIds.size })); setSelectedIds(new Set()); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => toast.error(t('pagina_docs.error_en_operacion_masiva')),
  });

  const toggleSelect = (id: string) => setSelectedIds(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleTag = (t: string) => setActiveTags((p: string[]) => p.includes(t) ? p.filter((x: string) => x !== t) : [...p, t]);
  const selectAll = () => setSelectedIds(docs.length === selectedIds.size ? new Set() : new Set(docs.map(d => d.id)));

  return (
    <Page
      icon={<Files size={18} />}
      title={_t('documents.title')}
      subtitle={_t('documents.subtitle')}
      rightActions={
        <Button onClick={() => setShowUpload(true)}>
          <Plus size={13} /> {_t('documents.upload')}
        </Button>
      }
    >
      {/* KPIs */}
      <div className="ds-grid-stats">
        <KpiCard icon={Files}      label={t('pagina_docs.total_documentos')} value={stats.total} color="var(--accent)" sub={t('pagina_docs.en_la_plataforma')} />
        <KpiCard icon={FileClock}  label={t('pagina_docs.pendientes')} value={stats.pending} color="var(--warning)" sub={t('pagina_docs.requieren_revision')} />
        <KpiCard icon={FileCheck}  label={t('pagina_docs.aprobados')} value={stats.approved} color="var(--success)" sub={t('pagina_docs.documentos_validos')} />
        <KpiCard icon={FileMinus}  label={t('documents.sin_aprobacion')} value={stats.noApproval} color="var(--text-3)" sub={t('pagina_docs.no_requieren_revision')} />
        <KpiCard icon={TrendingUp} label={t('documents.esta_semana')} value={stats.thisWeek} color="var(--purple)" sub={t('pagina_docs.nuevos_documentos')} />
      </div>

      {/* Filter bar — toolbar plana, sin caja contenedora (consistente con
          TasksPage / ProjectsPage / TicketListTab) */}
      <div className="ds-toolbar">
        <div className="docs-box-36">
          <Search size={14} aria-hidden className="docs-box-44" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('documents.buscar_por_titulo_archivo_o_etiqueta')}
            aria-label={t('pagina_docs.buscar_documentos')}
            className="ds-input docs-input-4"
            />
        </div>
        <select value={filterCat} onChange={e => setFilterCat(e.target.value)}
          aria-label={t('documents.filtrar_por_categoria')}
          className="ds-input docs-input-5">
          <option value="">{t('documents.todas_las_categorias')}</option>
          {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          aria-label={t('documents.filtrar_por_estado_de_aprobacion')}
          className="ds-input docs-input-5">
          <option value="">{t('documents.todos_los_estados')}</option>
          <optgroup label={t('documents.estado_de_aprobacion')}>
            <option value="pending">{t('pagina_docs.pendientes')}</option>
            <option value="approved">{t('pagina_docs.aprobados')}</option>
            <option value="rejected">{t('pagina_docs.rechazados')}</option>
          </optgroup>
          <optgroup label={t('pagina_docs.otros')}>
            <option value="no_approval">{t('documents.sin_aprobacion_requerida')}</option>
          </optgroup>
        </select>
        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
          aria-label={t('pagina_docs.ordenar')}
          className="ds-input docs-input-5">
          {SORT_OPTS.map(o => <option key={o.v} value={o.v}>{t(o.l)}</option>)}
        </select>
        <div className="ds-toolbar__spacer" />
        <div className="ds-segmented" role="group" aria-label={t('pagina_docs.vista')}>
          <button aria-label={t('pagina_docs.tarjetas')} type="button" aria-pressed={viewMode === 'grid'} onClick={() => setViewMode('grid')} title={t('pagina_docs.tarjetas')}>
            <Grid3X3 size={12} />
          </button>
          <button aria-label={t('pagina_docs.lista')} type="button" aria-pressed={viewMode === 'list'} onClick={() => setViewMode('list')} title={t('pagina_docs.lista')}>
            <List size={12} />
          </button>
        </div>
      </div>

      {/* Tag chips */}
      {allTags.length > 0 && (
        <div className="ds-row-wrap">
          {allTags.map(t => (
            <button key={t} onClick={() => toggleTag(t)}
              className={`ds-pill${activeTags.includes(t) ? ' ds-pill--accent' : ''} docs-btn-28`}
             >
              #{t}
            </button>
          ))}
          {activeTags.length > 0 && (
            <button onClick={() => setActiveTags([])}
              className="ds-pill ds-pill--danger docs-btn-28"
             >
              {t('pagina_docs.limpiar')}
            </button>
          )}
        </div>
      )}

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div className="docs-row-38">
          <span className="docs-label-14">
            {selectedIds.size}{' '}{t('pagina_docs.seleccionado_s')}
          </span>
          <Button size="sm" variant="danger"
            disabled={bulkDeleteMutation.isPending}
            onClick={() => { openConfirmGlobal({ message: t('pagina_docs.eliminar_documento_s', { size: selectedIds.size }), onConfirm: () => bulkDeleteMutation.mutate(), danger: true }) }}>
            <Trash2 size={12} />{' '}{t('pagina_docs.eliminar_seleccionados')}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setSelectedIds(new Set())}>
            {t('pagina_docs.cancelar')}
          </Button>
        </div>
      )}

      {/* Count */}
      <div className="ds-muted u-sm">
        {isLoading ? t('pagina_docs.cargando') : ((search || filterCat || filterStatus || activeTags.length)
          ? t(docs.length === 1 ? 'pagina_docs.documentos_uno_filtrado' : 'pagina_docs.documentos_otros_filtrado', { n: docs.length })
          : t(docs.length === 1 ? 'pagina_docs.documentos_uno' : 'pagina_docs.documentos_otros', { n: docs.length }))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="ds-grid-cards">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="docs-card-10" />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <div className="ds-empty">
          <FolderOpen size={36} className="ds-empty__icon" />
          <div className="ds-empty__title">{t('documents.no_documents')}</div>
          <div className="ds-empty__desc">
            {search || filterCat ? t('pagina_docs.no_hay_resultados_para_los_filtros') : t('pagina_docs.sube_tu_primer_documento_con_el')}
          </div>
          {!search && !filterCat && (
            <div className="docs-box-37">
              <Button onClick={() => setShowUpload(true)}>
                <Upload size={14} />{' '}{t('pagina_docs.subir_primer_documento')}
              </Button>
            </div>
          )}
        </div>
      ) : viewMode === 'grid' ? (
        <div className="ds-grid-cards docs-box-38">
          {docs.map(doc => (
            <DocCard key={doc.id} doc={doc}
              onView={setDrawerDocId}
              onDelete={d => { openConfirmGlobal({ message: t('pagina_docs.eliminar', { title: d.title }), onConfirm: () => deleteMutation.mutate(d.id), danger: true }) }}
              onSummary={summaryMutation.mutate}
              selected={selectedIds.has(doc.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      ) : (
        <div className="ds-card docs-box-39">
          <table className="u-table">
            <thead>
              <tr className="docs-row-39">
                <th className="docs-td">
                  <button type="button" onClick={selectAll}
                    className={`docs-btn-29 document-sx16 ${selectedIds.size === docs.length && docs.length > 0 ? 'document-sx12' : 'document-sx17'} documents-page-e4`} style={{ '--documents-page-border': `2px solid ${selectedIds.size === docs.length && docs.length > 0 ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
                    {selectedIds.size === docs.length && docs.length > 0 && <Check size={9} color="white" strokeWidth={3} />}
                  </button>
                </th>
                <th aria-hidden="true" className="docs-th" />
                {[t('pagina_docs.documento'), t('pagina_docs.categoria'), t('pagina_docs.aprobacion'), t('pagina_docs.tamano'), t('pagina_docs.fecha'), t('pagina_docs.autor'), ''].map(h => (
                  <th key={h} className="docs-th-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <DocRow key={doc.id} doc={doc}
                  onView={setDrawerDocId}
                  onDelete={d => { openConfirmGlobal({ message: t('pagina_docs.eliminar', { title: d.title }), onConfirm: () => deleteMutation.mutate(d.id), danger: true }) }}
                  onSummary={summaryMutation.mutate}
                  selected={selectedIds.has(doc.id)}
                  onToggleSelect={toggleSelect}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <UploadModal open={showUpload} onClose={() => setShowUpload(false)}
        onSuccess={() => { setShowUpload(false); qc.invalidateQueries({ queryKey: ['documents'] }); }} />

      {drawerDocId && (
        <DocumentDrawer documentId={drawerDocId} onClose={() => setDrawerDocId(null)}
          onRefresh={() => qc.invalidateQueries({ queryKey: ['documents'] })} />
      )}
    </Page>
  );
}
