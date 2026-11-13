/**
 * DocumentsPage — Rediseño completo del hub de gestión documental
 * Diseo integrado con el sistema visual de Contecflow (surface vars, accent, etc.)
 * Funcionalidades: KPIs, grid/tabla, drawer de detalle, carga modal dos columnas,
 * acciones bulk, etiquetas, aprobaciones, historial de versiones, resmenes IA
 */
import _React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import type { CSSProperties, ReactNode, DragEvent } from 'react';
import { useId } from 'react'
import type { AxiosError } from 'axios';
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api, { documentsApi, projectsApi, usersApi, type ApiError, type PathId } from '../services/api';
import { useToast } from '../context/ToastContext';
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

function relTime(d: string | null | undefined) {
  if (!d) return '';
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 2) return 'ahora';
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  const days = Math.floor(h / 24);
  if (days === 1) return 'ayer';
  if (days < 7) return `hace ${days}d`;
  if (days < 30) return `hace ${Math.floor(days / 7)}sem`;
  return `hace ${Math.floor(days / 30)}mes`;
}

const FILE_COLORS: Record<string, { c: string; bg: string; label: string }> = {
  pdf:          { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 9%, transparent)', label: 'PDF' },
  image:        { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 9%, transparent)', label: 'IMG' },
  spreadsheet:  { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 9%, transparent)', label: 'XLS' },
  word:         { c: 'var(--accent)', bg: '#6366f118', label: 'DOC' },
  presentation: { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 9%, transparent)', label: 'PPT' },
  archive:      { c: 'var(--purple)', bg: '#8b5cf618', label: 'ZIP' },
  text:         { c: '#64748b', bg: '#64748b18', label: 'TXT' },
  other:        { c: 'var(--text-3)', bg: '#6b728018', label: 'FILE' },
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
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.22),
      backgroundColor: ft.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      fontFamily: 'var(--font-mono)', fontSize: Math.round(size * 0.23),
      fontWeight: 700, color: ft.c, letterSpacing: '-0.03em',
    }}>
      {ft.label}
    </div>
  );
}

const CAT_STYLE: Record<string, { c: string; bg: string }> = {
  contract:     { c: 'var(--accent)', bg: 'color-mix(in srgb, var(--accent) 8%, transparent)' },
  deliverable:  { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 8%, transparent)' },
  proposal:     { c: 'var(--purple)', bg: '#8b5cf615' },
  sop:          { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 8%, transparent)' },
  legal:        { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 8%, transparent)' },
  requirements: { c: 'var(--chart-teal)', bg: '#06b6d415' },
  report:       { c: 'var(--orange)', bg: '#f9731615' },
  presentation: { c: 'var(--chart-pink)', bg: 'color-mix(in srgb, var(--chart-pink) 8%, transparent)' },
  meeting_notes:{ c: 'var(--sky-blue)', bg: '#0ea5e915' },
  other:        { c: 'var(--text-3)', bg: '#6b728015' },
};

const APPROVAL_STYLE: Record<string, { c: string; bg: string; icon: string; label: string }> = {
  approved: { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 8%, transparent)', icon: '\u2713', label: 'Aprobado' },
  rejected: { c: 'var(--danger)', bg: 'color-mix(in srgb, var(--danger) 8%, transparent)', icon: '\u2715', label: 'Rechazado' },
  pending:  { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 8%, transparent)', icon: '\u25f7', label: 'Pendiente' },
};

function Chip({ text, color, bg }: { text: ReactNode; color?: string; bg?: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20,
      backgroundColor: bg, color, textTransform: 'uppercase', letterSpacing: '0.04em',
      whiteSpace: 'nowrap',
    }}>
      {text}
    </span>
  );
}

// ── KPI card ─────────────────────────────────────────

function KpiCard({ icon: Icon, label, value, color, sub }: { icon: LucideIcon; label?: ReactNode; value?: ReactNode; color?: string; sub?: ReactNode }) {
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 11, flexShrink: 0,
        backgroundColor: alpha(color, '20'), display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: 'var(--text-1)', fontFamily: 'var(--font-mono)', lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
        {sub && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 1 }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── Doc Card (Grid) ─────────────────────────────────────────

type Reserva = { user_id: string; user_name?: string; at?: string; expires_at?: string; mine?: boolean } | null | undefined

/** `DocumentVersionOut` (app/schemas/documents.py). */
interface DocVersion {
  id: string
  version_num: number
  file_name: string
  file_size?: number | null
  file_mime_type?: string | null
  change_note?: string | null
  uploader_id?: string
  uploader_name?: string
  created_at?: string
  download_url?: string | null
  s3_url?: string | null
}

/** `DocumentListOut` (app/schemas/documents.py). */
interface DocListItem {
  id: string
  title: string
  category: string
  is_archived?: boolean
  requires_approval?: boolean
  approval_status?: string | null
  created_by_name?: string
  created_at: string
  updated_at?: string | null
  latest_version?: DocVersion | null
  checkout?: Reserva
  // `DocumentListOut` los declara desde la auditoría 2026-11; antes el response_model
  // los filtraba y las etiquetas, su filtro y la insignia «vN» no salían nunca.
  tags?: string[]
  version_count?: number
}

/** Decisión de un paso en `approval_request.decisions`. */
interface ApprovalDecision {
  decision: string
  approver_name?: string | null
  step_order?: number
  decided_at?: string | null
  note?: string | null
}

/** `DocumentOut.approval_request` (dict en el backend). */
interface ApprovalRequest {
  workflow_name?: string
  status?: string
  total_steps?: number
  current_step?: number
  current_step_name?: string | null
  current_approver_name?: string | null
  current_approver_role?: string | null
  decisions?: ApprovalDecision[]
}

/** `DocumentOut` (app/schemas/documents.py). */
interface DocDetail extends DocListItem {
  description?: string | null
  ai_summary?: string | null
  approved_by_name?: string | null
  approved_at?: string | null
  versions?: DocVersion[]
  tags?: string[]
  approval_request?: ApprovalRequest | null
}

/** `DocumentPermissionOut` (app/schemas/documents.py). */
interface DocPermission {
  id: string
  user_id?: string | null
  user_name?: string | null
  role?: string | null
  department?: string | null
  access_level: string
  granted_by_name?: string | null
  granted_at?: string
  expires_at?: string | null
}

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
  if (!reserva) return null
  return (
    <div title={reserva.expires_at ? t('documents.reserva_hasta', { fecha: new Date(reserva.expires_at).toLocaleString() }) : undefined}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 3, fontSize: "var(--text-2xs)", fontWeight: 600,
        color: reserva.mine ? 'var(--accent)' : 'var(--warning)' }}>
      <Lock size={10} /> {reserva.mine ? t('documents.reserva_tuya') : t('documents.reserva_de', { nombre: reserva.user_name || '—' })}
    </div>
  )
}

function DocCard({ doc, onView, onDelete, onSummary, selected, onToggleSelect }: DocItemProps) {
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
      style={{
        background: 'var(--surface-2)',
        border: `1px solid ${selected ? 'var(--accent)' : hover ? 'var(--surface-5)' : 'var(--surface-4)'}`,
        borderRadius: 12, cursor: 'pointer',
        transition: 'border-color 0.15s, box-shadow 0.15s',
        boxShadow: hover ? '0 6px 24px rgba(0,0,0,0.18)' : 'none',
        display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative',
      }}>

      {/* Top color strip */}
      <div style={{ height: 3, backgroundColor: ft.c, flexShrink: 0 }} />

      {/* Checkbox */}
      <button
        type="button"
        onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }}
        style={{
          position: 'absolute', top: 10, left: 10, zIndex: 2,
          width: 17, height: 17, borderRadius: 5,
          border: `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}`,
          backgroundColor: selected ? 'var(--accent)' : 'var(--surface-1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'all 0.12s', opacity: selected || hover ? 1 : 0,
          padding: 0, cursor: 'pointer',
        }}>
        {selected && <Check size={9} color="white" strokeWidth={3} />}
      </button>

      {/* Body */}
      <div style={{ padding: '14px 14px 10px', flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={42} />
          <div className="u-flex1-min0">
            <div style={{
              fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.35,
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
            }}>{doc.title}</div>
            <ReservaChip reserva={doc.checkout} />
            {lv?.file_name && (
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2, fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {lv.file_name}
              </div>
            )}
          </div>
        </div>

        {/* Badges */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          <Chip text={doc.category} color={catS.c} bg={catS.bg} />
          {doc.requires_approval && (() => {
            const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
            return <Chip text={`${a.icon} ${a.label}`} color={a.c} bg={a.bg} />;
          })()}
          {(doc.version_count || 0) > 1 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: "var(--text-2xs)", fontWeight: 600,
              padding: '2px 7px', borderRadius: 20, backgroundColor: 'var(--surface-3)', color: 'var(--text-3)',
            }}>
              <History size={9} /> v{doc.version_count}
            </span>
          )}
        </div>

        {/* Tags */}
        {doc.tags?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {doc.tags.slice(0, 3).map(t => (
              <span key={t} style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--surface-3)', color: 'var(--text-3)' }}>
                #{t}
              </span>
            ))}
            {doc.tags.length > 3 && <span className="u-text3-2xs">+{doc.tags.length - 3}</span>}
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: '8px 14px 10px', borderTop: '1px solid var(--surface-4)',
        backgroundColor: 'var(--surface-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div>
          <div className="u-text3-2xs">{relTime(doc.created_at)}</div>
          {lv && <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{fmtBytes(lv.file_size)}</div>}
        </div>
        <div style={{ display: 'flex', gap: 3, opacity: hover ? 1 : 0, transition: 'opacity 0.15s' }}>
          {lv?.download_url && (
            <a href={lv.download_url} target="_blank" rel="noreferrer" title="Descargar documento"
              onClick={e => e.stopPropagation()}
              style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none' }}>
              <Download size={11} />
            </a>
          )}
          <button aria-label="Generar resumen IA" onClick={(e) => { e.stopPropagation(); onSummary(doc.id); }} title="Generar resumen IA"
            style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--purple)' }}>
            <Sparkles size={11} />
          </button>
          <button aria-label="Eliminar documento" onClick={(e) => { e.stopPropagation(); onDelete(doc); }} title="Eliminar documento"
            style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
            <Trash2 size={11} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Doc Row (Table) ─────────────────────────────────────────

function DocRow({ doc, onView, onDelete, onSummary, selected, onToggleSelect }: DocItemProps) {
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
      style={{
        backgroundColor: selected ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : hover ? 'var(--surface-2)' : 'transparent',
        cursor: 'pointer', transition: 'background 0.1s',
        borderBottom: '1px solid var(--surface-4)',
      }}>
      <td style={{ padding: '10px 14px', width: 36 }}>
        <button type="button" onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }} style={{
          width: 16, height: 16, borderRadius: 4,
          border: `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}`,
          backgroundColor: selected ? 'var(--accent)' : 'transparent',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: 0, cursor: 'pointer',
        }}>
          {selected && <Check size={9} color="white" strokeWidth={3} />}
        </button>
      </td>
      <td style={{ padding: '10px 6px', width: 38 }}>
        <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
      </td>
      <td style={{ padding: '10px 12px', maxWidth: 280 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
        <ReservaChip reserva={doc.checkout} />
        {lv?.file_name && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{lv.file_name}</div>}
      </td>
      <td className="u-pad-10-12">
        <Chip text={doc.category} color={catS.c} bg={catS.bg} />
      </td>
      <td className="u-pad-10-12">
        {doc.requires_approval ? (() => {
          const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
          return <Chip text={`${a.icon} ${a.label}`} color={a.c} bg={a.bg} />;
        })() : <span className="u-text3-xs">—</span>}
      </td>
      <td style={{ padding: '10px 12px', fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
        {lv ? fmtBytes(lv.file_size) : '—'}
      </td>
      <td style={{ padding: '10px 12px', fontSize: "var(--text-xs)", color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{fmtDate(doc.created_at)}</td>
      <td style={{ padding: '10px 12px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{doc.created_by_name || '—'}</td>
      <td style={{ padding: '10px 12px', width: 90 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', gap: 3, opacity: hover ? 1 : 0, transition: 'opacity 0.1s' }}>
          {lv?.download_url && (
            <a href={lv.download_url} target="_blank" rel="noreferrer"
              style={{ width: 24, height: 24, borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none' }}>
              <Download size={11} />
            </a>
          )}
          <button onClick={() => onSummary(doc.id)}
            style={{ width: 24, height: 24, borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--purple)' }}>
            <Sparkles size={11} />
          </button>
          <button onClick={() => onDelete(doc)}
            style={{ width: 24, height: 24, borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
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
    staleTime: 30000,
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
    onSuccess: () => { toast.success('Documento subido correctamente'); onSuccess(); },
    onError: (e: ApiError) => toast.error(detalleDeError(e) || 'Error al subir'),
  });

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); }
  }, []);

  const pickFile = (f: File) => { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); };
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose);

  if (!open) return null;

  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 };
  const fileType = file ? detectFileType(undefined, file.name) : null;
  const fileFt = fileType ? FILE_COLORS[fileType] : null;

  return (
    <div role="presentation" style={{ position: 'fixed', inset: 0, zIndex: 'var(--z-modal)', backgroundColor: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }} onMouseDown={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="upload-dialog-title" style={{ background: 'var(--surface-1)', borderRadius: 16, width: '100%', maxWidth: 740, border: '1px solid var(--surface-4)', boxShadow: '0 24px 64px rgba(0,0,0,0.5)', overflow: 'hidden' }} onMouseDown={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '18px 24px', borderBottom: '1px solid var(--surface-4)' }}>
          <div>
            <div id="upload-dialog-title" style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: 'var(--text-1)' }}>Subir documento</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 2 }}>{t('documents.arrastra_un_archivo_o_haz_clic_para')}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 6 }}>
            <X size={18} />
          </button>
        </div>

        {/* Body: dos columnas */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          {/* Izquierda: zona de carga */}
          <div style={{ padding: 24, borderRight: '1px solid var(--surface-4)' }}>
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
              style={{
                border: `2px dashed ${dragOver ? 'var(--accent)' : file ? (fileFt?.c || 'var(--success)') : 'var(--surface-5)'}`,
                borderRadius: 12, padding: '28px 16px', textAlign: 'center', cursor: 'pointer',
                backgroundColor: dragOver ? 'var(--surface-2)' : 'transparent', transition: 'all 0.15s',
                minHeight: 220, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
              }}>
              <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f); }} />
              {file ? (
                <>
                  <FileIcon mime={undefined} name={file.name} size={56} />
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', wordBreak: 'break-all', maxWidth: 200 }}>{file.name}</div>
                  <div className="u-text3-mono-xs">{fmtBytes(file.size)}</div>
                  <button onClick={e => { e.stopPropagation(); setFile(null); }}
                    style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 4 }}>
                    Cambiar archivo 
                  </button>
                </>
              ) : (
                <>
                  <div style={{ width: 56, height: 56, borderRadius: 'var(--radius-lg)', backgroundColor: 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Upload size={22} style={{ color: 'var(--text-3)' }} />
                  </div>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-2)' }}>Arrastra aqutu archivo</div>
                  <div className="u-text3-xs">{t('documents.o_haz_clic_para_seleccionar')}</div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 4 }}>{t('documents.pdf_word_excel_imagenes_max_100_mb')}</div>
                </>
              )}
            </div>
          </div>

          {/* Derecha: metadatos */}
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 13 }}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('documents.titulo')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} style={fs} placeholder={file?.name || 'Título del documento'} />
            </div>
            <div>
              <label style={ls}>{t('documents.descripcion')}</label>
              <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={2} style={{ ...fs, resize: 'none' }} placeholder={t('documents.descripcion_del_documento')} aria-label={t('documents.descripcion_del_documento')} />
            </div>
            <div className="u-grid2-10">
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('documents.categoria')}</label>
                <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} style={fs}>
                  {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Proyecto</label>
                <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.project_id} onChange={e => setForm(p => ({ ...p, project_id: e.target.value }))} style={fs}>
                  <option value="">{t('documents.sin_proyecto')}</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} - ` : ''}{p.name}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label style={ls}>Etiquetas</label>
              <input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} style={fs} placeholder={t('documents.etiquetas_separadas_por_comas')} aria-label={t('documents.etiquetas_separadas_por_comas')} />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={form.requires_approval} onChange={e => setForm(p => ({ ...p, requires_approval: e.target.checked }))}
                style={{ width: 15, height: 15, accentColor: 'var(--accent)' }} />
              <span className="u-text2-base">{t('documents.requiere_aprobacion_antes_de_usar')}</span>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 24px', borderTop: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'flex-end', gap: 10, backgroundColor: 'var(--surface-2)' }}>
          <button onClick={onClose} style={{ padding: '9px 20px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit' }}>
            Cancelar
          </button>
          <button onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
            style={{ padding: '9px 22px', borderRadius: 8, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: "var(--text-base)", fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 7 }}>
            {uploadMutation.isPending ? <><Loader size={14} style={{ animation: 'spin 0.8s linear infinite' }} /> Subiendo...</> : <><Upload size={14} /> Subir documento</>}
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
  { v: 'viewer', l: 'Lector (abrir y descargar)' },
  { v: 'editor', l: 'Editor (subir versiones)' },
  { v: 'admin', l: 'Admin (gestionar permisos)' },
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
    staleTime: 60_000,
  });

  const departments = useMemo(() => {
    const s = new Set<string>();
    users.forEach(u => { if (u.department) s.add(u.department); });
    return [...s].sort();
  }, [users]);

  const grantMutation = useMutation({
    mutationFn: (payload: PermissionGrant) => documentsApi.grantPermission(documentId, payload),
    onSuccess: () => {
      toast.success('Permiso concedido');
      qc.invalidateQueries({ queryKey: ['document-permissions', documentId] });
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setUserId(''); setDeptVal(''); setExpiresAt('');
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'No se pudo conceder el permiso'),
  });

  const revokeMutation = useMutation({
    mutationFn: (permId: string) => documentsApi.revokePermission(documentId, permId),
    onSuccess: () => {
      toast.success('Permiso revocado');
      qc.invalidateQueries({ queryKey: ['document-permissions', documentId] });
      qc.invalidateQueries({ queryKey: ['document', documentId] });
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'No se pudo revocar'),
  });

  const submitGrant = () => {
    const payload: PermissionGrant = { access_level: accessLevel };
    if (expiresAt) payload.expires_at = new Date(expiresAt).toISOString();
    if (subjectType === 'user') {
      if (!userId) { toast.error('Selecciona un usuario'); return; }
      payload.user_id = userId;
    } else if (subjectType === 'role') {
      payload.role = roleVal;
    } else if (subjectType === 'department') {
      const d = (deptVal || '').trim();
      if (!d) { toast.error('Indica un departamento'); return; }
      payload.department = d;
    }
    grantMutation.mutate(payload);
  };

  const subjectLabel = (p: DocPermission) => {
    if (p.user_id) return `👤 ${p.user_name || p.user_id}`;
    if (p.role) return `🛡️ Rol: ${p.role}`;
    if (p.department) return `🏢 Departamento: ${p.department}`;
    return '—';
  };

  const inputStyle: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' };
  const labelStyle: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4, display: 'block' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 'var(--radius-md)', padding: '10px 14px', fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
        <strong>{t('documents.por_defecto')}</strong>{t('documents.el_creador_del_documento_y_los_miembros')}
      </div>

      {/* Add grant */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 14 }}>
        <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Share2 size={14} /> Conceder acceso
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 12 }}>
          {[
            { v: 'user', l: 'Usuario', icon: Users },
            { v: 'role', l: 'Rol' },
            { v: 'department', l: 'Departamento' },
          ].map(opt => (
            <button key={opt.v} onClick={() => setSubjectType(opt.v)}
              style={{
                padding: '8px 10px', borderRadius: 8,
                border: `1px solid ${subjectType === opt.v ? 'var(--accent)' : 'var(--surface-4)'}`,
                background: subjectType === opt.v ? 'var(--accent-muted)' : 'transparent',
                color: subjectType === opt.v ? 'var(--accent)' : 'var(--text-2)',
                fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              }}>
              {opt.l}
            </button>
          ))}
        </div>

        {subjectType === 'user' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Usuario</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={userId} onChange={e => setUserId(e.target.value)} style={inputStyle}>
              <option value="">{t('documents.selecciona_un_usuario')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
            </select>
          </div>
        )}
        {subjectType === 'role' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={labelStyle}>Rol</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={roleVal} onChange={e => setRoleVal(e.target.value)} style={inputStyle}>
              {ROLES_AVAILABLE.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        )}
        {subjectType === 'department' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={labelStyle}>Departamento</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="text" value={deptVal} onChange={e => setDeptVal(e.target.value)}
              list="departments-list" placeholder="ej. Finance"
              style={inputStyle} />
            <datalist id="departments-list">
              {departments.map(d => <option key={d} value={d} />)}
            </datalist>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={labelStyle}>{t('documents.nivel_de_acceso')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={accessLevel} onChange={e => setAccessLevel(e.target.value)} style={inputStyle}>
              {ACCESS_LEVELS.map(a => <option key={a.v} value={a.v}>{a.l}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={labelStyle}>Caducidad (opcional)</label>
            <DateInput id={`${idCampo}-5`} withTime value={expiresAt} onChange={e => setExpiresAt(e.target.value)} style={inputStyle} />
          </div>
        </div>

        <button onClick={submitGrant} disabled={grantMutation.isPending}
          style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', fontWeight: 700, fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Check size={13} /> {grantMutation.isPending ? 'Concediendo…' : 'Conceder acceso'}
        </button>
      </div>

      {/* Existing grants */}
      <div>
        <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: 8 }}>
          Permisos actuales <span style={{ color: 'var(--text-3)', fontWeight: 400, fontSize: 'var(--text-xs)' }}>({perms.length})</span>
        </div>
        {perms.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)', border: '1px dashed var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
            {t('documents.sin_permisos_explicitos_solo_el_creador_y')}
          </div>
        ) : (
          <div className="u-stack-6">
            {perms.map(p => (
              <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
                <div className="u-flex1-min0">
                  <div className="u-text1-sm-600">{subjectLabel(p)}</div>
                  <div className="u-text3-2xs">
                    {ACCESS_LEVELS.find(a => a.v === p.access_level)?.l || p.access_level}
                    {p.granted_by_name && ` · concedido por ${p.granted_by_name}`}
                    {p.expires_at && ` · caduca ${new Date(p.expires_at).toLocaleDateString(localeActivo())}`}
                  </div>
                </div>
                <button onClick={() => revokeMutation.mutate(p.id)} disabled={revokeMutation.isPending}
                  style={{ padding: '5px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--danger)', fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Trash2 size={11} /> Revocar
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
    onSuccess: (_: unknown, { status }: { status: string }) => { toast.success(status === 'approved' ? 'Paso aprobado' : 'Documento rechazado'); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error'),
  });

  const submitApprovalMutation = useMutation({
    mutationFn: () => documentsApi.submitApproval(documentId),
    onSuccess: () => { toast.success('Solicitud de aprobación enviada'); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'No hay ningún flujo de aprobación configurado para esta categoría'),
  });

  const summaryMutation = useMutation({
    mutationFn: () => documentsApi.aiSummary(documentId),
    onSuccess: () => {
      toast.success('Resumen IA generado');
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setTab('meta');
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error IA'),
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
      toast.error(typeof d === 'string' ? d : d?.message || 'Error')
    },
  });

  const versionMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file!);
      if (changeNote) fd.append('change_note', changeNote);
      return documentsApi.addVersion(documentId, fd);
    },
    onSuccess: () => { toast.success('Nueva versión subida'); qc.invalidateQueries({ queryKey: ['document', documentId] }); setFile(null); setChangeNote(''); setShowUploadVersion(false); onRefresh(); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error'),
  });

  const updateMetaMutation = useMutation({
    mutationFn: (data: MetaForm) => documentsApi.update(documentId, data),
    onSuccess: () => {
      toast.success('Metadatos actualizados');
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      qc.invalidateQueries({ queryKey: ['documents'] });
      setIsEditingMeta(false);
      onRefresh();
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error al guardar'),
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

  const tabBtnStyle = (id: string): CSSProperties => ({
    padding: '6px 14px', borderRadius: 7, border: `1px solid ${tab === id ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}`,
    backgroundColor: tab === id ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'transparent',
    color: tab === id ? 'var(--accent)' : 'var(--text-2)',
    fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.12s',
  });

  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };

  return (
    <Drawer onClose={onClose} ariaLabel={doc?.title || 'Documento'} width={600} zIndex={900}>
        {isLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
            <Loader size={18} style={{ animation: 'spin 0.8s linear infinite', marginRight: 8 }} /> Cargando...
          </div>
        ) : !doc ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: 'var(--danger)', fontSize: "var(--text-base)" }}>{t('documents.documento_no_encontrado')}</div>
        ) : (
          <>
            {/* Drawer header */}
            <div style={{ padding: '18px 22px 14px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
                <div className="u-flex1-min0">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    <FileIcon mime={activeVer?.file_mime_type} name={activeVer?.file_name} size={38} />
                    <div className="u-flex1-min0">
                      <h2 style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: 'var(--text-1)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</h2>
                      {doc.description && <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.description}</p>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    <Chip text={doc.category} color={catS!.c} bg={catS!.bg} />
                    {doc.requires_approval && (() => {
                      const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
                      return <Chip text={`${a.icon} ${a.label}`} color={a.c} bg={a.bg} />;
                    })()}
                    {doc.tags?.map(t => (
                      <span key={t} style={{ fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--surface-3)', color: 'var(--text-3)' }}>#{t}</span>
                    ))}
                  </div>
                </div>
                <button onClick={onClose} aria-label="Cerrar" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4, flexShrink: 0 }}>
                  <X size={18} />
                </button>
              </div>

              {/* Action row */}
              <div className="u-wrap-8">
                {doc.requires_approval && doc.approval_status === 'pending' && !doc.approval_request && (
                  <button
                    onClick={() => submitApprovalMutation.mutate()}
                    disabled={submitApprovalMutation.isPending}
                    style={{ padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--warning)', color: 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}
                  >
                    <FileClock size={13} /> {submitApprovalMutation.isPending ? 'Enviando...' : 'Enviar para aprobación'}
                  </button>
                )}
                {doc.requires_approval && doc.approval_status === 'rejected' && (
                  <button
                    onClick={() => submitApprovalMutation.mutate()}
                    disabled={submitApprovalMutation.isPending}
                    title={t('documents.reabre_un_nuevo_flujo_de_aprobacion_el')}
                    style={{ padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--warning)', color: 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}
                  >
                    <FileClock size={13} /> {submitApprovalMutation.isPending ? 'Reenviando...' : 'Reenviar a aprobación'}
                  </button>
                )}
                {doc.requires_approval && doc.approval_status === 'pending' && doc.approval_request?.status === 'pending' && (
                  <>
                    <button onClick={() => approveMutation.mutate({ status: 'approved' })} disabled={approveMutation.isPending} style={{ padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--success)', color: 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <CheckCircle size={13} /> Aprobar paso
                    </button>
                    <button onClick={() => approveMutation.mutate({ status: 'rejected' })} disabled={approveMutation.isPending} style={{ padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--danger)', color: 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <XCircle size={13} /> Rechazar
                    </button>
                  </>
                )}
                {!reserva && (
                  <button onClick={() => reservaMutation.mutate('checkout')} disabled={reservaMutation.isPending}
                    title={t('documents.reserva_ayuda')}
                    style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-1)', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Lock size={13} /> {t('documents.reservar')}
                  </button>
                )}
                {reserva?.mine && (
                  <button onClick={() => reservaMutation.mutate('checkin')} disabled={reservaMutation.isPending}
                    style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--accent)', backgroundColor: 'transparent', color: 'var(--accent)', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <LockOpen size={13} /> {t('documents.liberar')}
                  </button>
                )}
                <button onClick={() => summaryMutation.mutate()} disabled={summaryMutation.isPending}
                  style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--purple)', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                   <Sparkles size={13} /> {summaryMutation.isPending ? 'Generando...' : 'Resumen IA'}
                </button>
                {activeVer?.download_url && (
                  <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                    style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-sm)", fontWeight: 700, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Download size={13} /> Descargar
                  </a>
                )}
              </div>
            </div>

            {deOtro && (
              <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 22px', backgroundColor: 'color-mix(in srgb, var(--warning) 12%, transparent)', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
                <Lock size={14} color="var(--warning)" />
                <span className="u-flex1">
                  {t('documents.reserva_aviso', { nombre: reserva?.user_name || '—', fecha: reserva?.expires_at ? new Date(reserva.expires_at).toLocaleString() : '—' })}
                </span>
                <button onClick={() => reservaMutation.mutate('force')} disabled={reservaMutation.isPending}
                  style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                  {t('documents.reserva_forzar')}
                </button>
              </div>
            )}

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 6, padding: '12px 22px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
              <button style={tabBtnStyle('preview')} onClick={() => setTab('preview')}>
                <Eye size={12} style={{ display: 'inline', marginRight: 4 }} /> Vista previa
              </button>
              <button style={tabBtnStyle('versions')} onClick={() => setTab('versions')}>
                <History size={12} style={{ display: 'inline', marginRight: 4 }} />
                Versiones {(doc.versions?.length ?? 0) > 0 && `(${doc.versions.length})`}
              </button>
              <button style={tabBtnStyle('meta')} onClick={() => setTab('meta')}>
                <Info size={12} style={{ display: 'inline', marginRight: 4 }} /> Metadatos
              </button>
              <button style={tabBtnStyle('share')} onClick={() => setTab('share')}>
                <Share2 size={12} style={{ display: 'inline', marginRight: 4 }} /> Compartir
              </button>
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 22 }}>

              {/* Preview */}
              {tab === 'preview' && activeVer?.download_url && (
                <div style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
                  <div style={{ padding: '8px 14px', backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="u-text3-xs">{activeVer.file_name} · {fmtBytes(activeVer.file_size)}</span>
                    <a href={activeVer.download_url} target="_blank" rel="noreferrer" style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
                       <ExternalLink size={11} /> {t('documents.abrir_en_nueva_pestana')}
                    </a>
                  </div>
                  {(() => {
                    if (previewError) return (
                      <div style={{ padding: 40, textAlign: 'center' }}>
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div style={{ marginTop: 14, fontSize: "var(--text-base)", color: 'var(--text-3)' }}>{t('documents.el_archivo_no_esta_disponible_en_el')}</div>
                        {activeVer.download_url && (
                          <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 12, padding: '8px 16px', borderRadius: 8, backgroundColor: 'var(--accent)', color: 'var(--on-accent)', textDecoration: 'none', fontSize: "var(--text-base)", fontWeight: 700 }}>
                            <Download size={14} /> Intentar descargar
                          </a>
                        )}
                      </div>
                    );
                    const type = detectFileType(activeVer.file_mime_type, activeVer.file_name);
                    if (type === 'pdf') return <iframe src={activeVer.download_url} style={{ width: '100%', height: 480, border: 'none' }} title={t('documents.vista_previa_del_pdf')} onError={() => setPreviewError(true)} />;
                    if (type === 'image') return <img src={activeVer.download_url} alt={activeVer.file_name} loading="lazy" decoding="async" style={{ maxWidth: '100%', maxHeight: 480, objectFit: 'contain', display: 'block', margin: '0 auto', padding: 16 }} onError={() => setPreviewError(true)} />;
                    return (
                      <div style={{ padding: 40, textAlign: 'center' }}>
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div style={{ marginTop: 14, fontSize: "var(--text-base)", color: 'var(--text-3)' }}>{t('documents.vista_previa_no_disponible_para_este_tipo')}</div>
                        <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 12, padding: '8px 16px', borderRadius: 8, backgroundColor: 'var(--accent)', color: 'var(--on-accent)', textDecoration: 'none', fontSize: "var(--text-base)", fontWeight: 700 }}>
                          <Download size={14} /> {t('documents.descargar_para_ver')}
                        </a>
                      </div>
                    );
                  })()}
                </div>
              )}
              {tab === 'preview' && !activeVer?.download_url && (
                <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
                  <FolderOpen size={36} style={{ display: 'block', margin: '0 auto 12px', opacity: 0.4 }} />
                  {t('documents.este_documento_no_tiene_archivo_adjunto_todavia')}
                </div>
              )}

              {/* Versions */}
              {tab === 'versions' && (
                <div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
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
                        style={{
                          display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 'var(--radius-md)', cursor: 'pointer',
                          backgroundColor: activeVer?.id === v.id ? 'var(--surface-3)' : 'var(--surface-2)',
                          border: `1px solid ${activeVer?.id === v.id ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}`,
                          transition: 'all 0.12s',
                        }}>
                        <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: activeVer?.id === v.id ? 'var(--accent)' : 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)', fontSize: "var(--text-xs)", fontWeight: 700, color: activeVer?.id === v.id ? 'white' : 'var(--text-2)', flexShrink: 0 }}>
                          v{v.version_num}
                        </div>
                        <div className="u-flex1-min0">
                          <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.file_name}</div>
                          {v.change_note && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.change_note}</div>}
                          <div className="u-text3-2xs">{v.uploader_name} · {fmtDate(v.created_at)} · {fmtBytes(v.file_size)}</div>
                        </div>
                        {i === 0 && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 8px', borderRadius: 'var(--radius-md)', backgroundColor: 'color-mix(in srgb, var(--accent) 13%, transparent)', color: 'var(--accent)', fontWeight: 700 }}>Actual</span>}
                        {v.download_url && (
                          <a href={v.download_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                            style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none', flexShrink: 0 }}>
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
                      style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: '1px dashed var(--surface-5)', backgroundColor: 'transparent', color: deOtro ? 'var(--text-3)' : 'var(--accent)', fontSize: "var(--text-base)", fontWeight: 600, cursor: deOtro ? 'not-allowed' : 'pointer', fontFamily: 'inherit', width: '100%', justifyContent: 'center' }}>
                      <Upload size={14} /> {t('documents.subir_nueva_version')}
                    </button>
                  ) : (
                    <div style={{ padding: 14, borderRadius: 'var(--radius-md)', border: '1px solid var(--surface-4)', backgroundColor: 'var(--surface-2)', display: 'flex', flexDirection: 'column', gap: 10 }}>
                      <div onClick={() => fileRef.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileRef.current?.click(); } }} style={{ border: `2px dashed ${file ? 'var(--success)' : 'var(--surface-5)'}`, borderRadius: 8, padding: '12px 16px', textAlign: 'center', cursor: 'pointer' }}>
                        {file ? <span className="u-text1-base-600">{file.name}</span>
                          : <span className="u-text3-sm"><Upload size={13} style={{ display: 'inline', marginRight: 4 }} />{t('documents.clic_para_seleccionar_archivo')}</span>}
                        <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={e => setFile(e.target.files?.[0] ?? null)} />
                      </div>
                      <input placeholder={t('documents.nota_del_cambio')} value={changeNote} onChange={e => setChangeNote(e.target.value)} style={fs} aria-label={t('documents.nota_del_cambio')} />
                      <div className="u-row-8">
                        <button onClick={() => versionMutation.mutate()} disabled={!file || versionMutation.isPending}
                          style={{ flex: 1, padding: '8px', borderRadius: 8, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: "var(--text-base)", fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit' }}>
                          {versionMutation.isPending ? 'Subiendo...' : 'Subir'}
                        </button>
                        <button onClick={() => { setShowUploadVersion(false); setFile(null); setChangeNote(''); }}
                          style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit' }}>
                          Cancelar
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
                    <div style={{ background: 'color-mix(in srgb, var(--purple) 7%, transparent)', border: '1px solid color-mix(in srgb, var(--purple) 19%, transparent)', borderRadius: 'var(--radius-md)', padding: '12px 16px', marginBottom: 16 }}>
                      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--purple)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Sparkles size={12} /> Resumen IA
                      </div>
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', lineHeight: 1.6 }}>{doc.ai_summary}</div>
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                    {([
                      ['Creado por', doc.created_by_name || '—'],
                      ['Fecha creación', fmtDate(doc.created_at)],
                      ['Categoría', doc.category],
                      ['Versiones', doc.versions?.length || 1],
                      ['Requiere aprob.', doc.requires_approval ? 'Sí' : 'No'],
                      ['Estado aprob.', doc.approval_status || '—'],
                      doc.approved_by_name && ['Aprobado por', doc.approved_by_name],
                      doc.approved_at && ['Fecha aprob.', fmtDate(doc.approved_at)],
                    ] as Array<[string, ReactNode] | null | undefined | ''>).filter((x): x is [string, ReactNode] => Boolean(x)).map(([k, v]) => (
                      <div key={k} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>{k}</div>
                        <div className="u-text1-base-600">{v}</div>
                      </div>
                    ))}
                    {doc.description && (
                      <div style={{ gridColumn: '1/-1', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>{t('documents.descripcion')}</div>
                        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.5 }}>{doc.description}</div>
                      </div>
                    )}
                    {(doc.tags?.length ?? 0) > 0 && (
                      <div style={{ gridColumn: '1/-1', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Etiquetas</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {doc.tags.map(t => (
                            <span key={t} style={{ fontSize: "var(--text-sm)", padding: '3px 10px', borderRadius: 12, backgroundColor: 'var(--surface-3)', color: 'var(--text-2)' }}>#{t}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <button onClick={() => {
                    setMetaForm({ title: doc.title || '', description: doc.description || '', category: doc.category || 'other', requires_approval: doc.requires_approval ?? false });
                    setIsEditingMeta(true);
                  }} style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-1)', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6 }}>
                    ✏️ Editar metadatos
                  </button>
                </div>
              )}
                    {/* Approval workflow panel */}
                    {doc.approval_request && (
                      <div style={{ marginTop: 16, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
                        <div style={{ fontWeight: 700, fontSize: "var(--text-sm)", color: 'var(--text-1)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <FileClock size={14} style={{ color: 'var(--warning)' }} />
                          {t('documents.flujo_de_aprobacion')} {doc.approval_request.workflow_name}
                        </div>
                        {/* Step indicator */}
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 4 }}>
                          {Array.from({ length: doc.approval_request.total_steps || 1 }, (_: unknown, i: number) => {
                            const stepNum = i + 1;
                            const isDone = stepNum < (doc.approval_request.current_step || 1);
                            const isCurrent = stepNum === (doc.approval_request.current_step || 1) && doc.approval_request.status === 'pending';
                            const isRejected = doc.approval_request.status === 'rejected';
                            const color = isDone ? 'var(--success)' : isCurrent ? '#f59e0b' : isRejected && stepNum === doc.approval_request.current_step ? 'var(--danger)' : 'var(--surface-4)';
                            return (
                              <div key={stepNum} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <div style={{ width: 28, height: 28, borderRadius: '50%', backgroundColor: color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: (isDone || isCurrent) ? 'white' : 'var(--text-3)' }}>
                                  {isDone ? '✓' : stepNum}
                                </div>
                                {stepNum < (doc.approval_request.total_steps || 1) && (
                                  <div style={{ width: 20, height: 2, backgroundColor: isDone ? 'var(--success)' : 'var(--surface-4)', borderRadius: 2 }} />
                                )}
                              </div>
                            );
                          })}
                          <span style={{ marginLeft: 8, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                            Paso {doc.approval_request.current_step} {t('documents.de')} {doc.approval_request.total_steps}
                          </span>
                        </div>
                        {/* Current step info */}
                        {doc.approval_request.status === 'pending' && doc.approval_request.current_step_name && (
                          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>
                            <span style={{ fontWeight: 700 }}>{doc.approval_request.current_step_name}</span>
                            {doc.approval_request.current_approver_name && (
                              <> {t('documents.pendiente_de')} <span className="u-accent">{doc.approval_request.current_approver_name}</span></>
                            )}
                            {!doc.approval_request.current_approver_name && doc.approval_request.current_approver_role && (
                              <> {t('documents.pendiente_de_rol')} <span className="u-accent">{doc.approval_request.current_approver_role}</span></>
                            )}
                          </div>
                        )}
                        {doc.approval_request.status === 'approved' && (
                          <div style={{ fontSize: "var(--text-sm)", color: 'var(--success)', fontWeight: 700 }}>✓ Aprobado completamente</div>
                        )}
                        {doc.approval_request.status === 'rejected' && (
                          <div style={{ fontSize: "var(--text-sm)", color: 'var(--danger)', fontWeight: 700 }}>✗ Rechazado</div>
                        )}
                        {/* Decisions trail */}
                        {(doc.approval_request.decisions?.length ?? 0) > 0 && (
                          <div style={{ marginTop: 10, borderTop: '1px solid var(--surface-4)', paddingTop: 10 }}>
                            <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{t('documents.historial_de_decisiones')}</div>
                            {doc.approval_request.decisions.map((d, idx) => (
                              <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                                <div style={{ width: 20, height: 20, borderRadius: '50%', backgroundColor: d.decision === 'approved' ? 'color-mix(in srgb, var(--success) 13%, transparent)' : 'color-mix(in srgb, var(--danger) 13%, transparent)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                  <span style={{ fontSize: 10, color: d.decision === 'approved' ? 'var(--success)' : 'var(--danger)' }}>{d.decision === 'approved' ? '✓' : '✗'}</span>
                                </div>
                                <div>
                                  <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-1)' }}>{d.approver_name || 'Desconocido'}</span>
                                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginLeft: 6 }}>Paso {d.step_order} · {d.decided_at ? new Date(d.decided_at).toLocaleDateString(localeActivo()) : ''}</span>
                                  {d.note && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2, fontStyle: 'italic' }}>"{d.note}"</div>}
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
                    <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>{t('documents.titulo')}</label>
                    <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={metaForm.title} onChange={e => setMetaForm(f => f && ({ ...f, title: e.target.value }))} style={fs} />
                  </div>
                  <div>
                    <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>{t('documents.descripcion')}</label>
                    <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={metaForm.description} onChange={e => setMetaForm(f => f && ({ ...f, description: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical', lineHeight: 1.6 }} />
                  </div>
                  <div>
                    <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>{t('documents.categoria')}</label>
                    <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={metaForm.category} onChange={e => setMetaForm(f => f && ({ ...f, category: e.target.value }))} style={fs}>
                      <option value="contract">Contrato</option>
                      <option value="deliverable">Entregable</option>
                      <option value="proposal">Propuesta</option>
                      <option value="sop">Procedimiento (SOP)</option>
                      <option value="requirements">Requisitos</option>
                      <option value="meeting_notes">{t('documents.notas_de_reunion')}</option>
                      <option value="legal">Legal</option>
                      <option value="other">Otro</option>
                    </select>
                  </div>
                  <div className="u-row-center-10">
                    <input type="checkbox" id="meta-req-approval" checked={metaForm.requires_approval} onChange={e => setMetaForm(f => f && ({ ...f, requires_approval: e.target.checked }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                    <label htmlFor="meta-req-approval" style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', cursor: 'pointer' }}>{t('documents.requiere_aprobacion')}</label>
                  </div>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 6, borderTop: '1px solid var(--surface-4)' }}>
                    <button onClick={() => setIsEditingMeta(false)} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>Cancelar</button>
                    <button onClick={() => updateMetaMutation.mutate(metaForm)} disabled={updateMetaMutation.isPending || !metaForm.title}
                      style={{ padding: '7px 16px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                      {updateMetaMutation.isPending ? 'Guardando...' : '💾 Guardar'}
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
  { v: 'date_desc', l: 'Más recientes' },
  { v: 'date_asc',  l: 'Más antiguos' },
  { v: 'name_asc',  l: 'A–Z' },
  { v: 'size_desc', l: 'Más grandes' },
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
      const p: { limit: number; category?: string; search?: string } = { limit: 200 };
      if (filterCat) p.category = filterCat;
      if (search) p.search = search;
      return documentsApi.list(p).then(r => Array.isArray(r.data) ? r.data : (r.data?.items ?? []));
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
    onSuccess: () => { toast.success('Documento eliminado'); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => toast.error('Error al eliminar'),
  });

  const summaryMutation = useMutation({
    mutationFn: (id: string) => documentsApi.aiSummary(id),
    onSuccess: () => { toast.success('Resumen IA generado'); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error IA'),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: () => Promise.all([...selectedIds].map(id => documentsApi.delete(id))),
    onSuccess: () => { toast.success(`${selectedIds.size} documento(s) eliminados`); setSelectedIds(new Set()); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => toast.error('Error en operación masiva'),
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
        <KpiCard icon={Files}      label="Total documentos" value={stats.total} color="var(--accent)" sub="en la plataforma" />
        <KpiCard icon={FileClock}  label="Pendientes" value={stats.pending} color="var(--warning)" sub="requieren revisión" />
        <KpiCard icon={FileCheck}  label="Aprobados" value={stats.approved} color="var(--success)" sub="documentos válidos" />
        <KpiCard icon={FileMinus}  label={t('documents.sin_aprobacion')} value={stats.noApproval} color="var(--text-3)" sub="no requieren revisión" />
        <KpiCard icon={TrendingUp} label={t('documents.esta_semana')} value={stats.thisWeek} color="var(--purple)" sub="nuevos documentos" />
      </div>

      {/* Filter bar — toolbar plana, sin caja contenedora (consistente con
          TasksPage / ProjectsPage / TicketListTab) */}
      <div className="ds-toolbar">
        <div style={{ position: 'relative', flex: '2 1 280px', minWidth: 200, maxWidth: 420 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('documents.buscar_por_titulo_archivo_o_etiqueta')}
            aria-label="Buscar documentos"
            className="ds-input"
            style={{ paddingLeft: 32 }} />
        </div>
        <select value={filterCat} onChange={e => setFilterCat(e.target.value)}
          aria-label={t('documents.filtrar_por_categoria')}
          className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
          <option value="">{t('documents.todas_las_categorias')}</option>
          {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          aria-label={t('documents.filtrar_por_estado_de_aprobacion')}
          className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
          <option value="">{t('documents.todos_los_estados')}</option>
          <optgroup label={t('documents.estado_de_aprobacion')}>
            <option value="pending">Pendientes</option>
            <option value="approved">Aprobados</option>
            <option value="rejected">Rechazados</option>
          </optgroup>
          <optgroup label="Otros">
            <option value="no_approval">{t('documents.sin_aprobacion_requerida')}</option>
          </optgroup>
        </select>
        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
          aria-label="Ordenar"
          className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
          {SORT_OPTS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        <div className="ds-toolbar__spacer" />
        <div className="ds-segmented" role="group" aria-label="Vista">
          <button aria-label="Tarjetas" type="button" aria-pressed={viewMode === 'grid'} onClick={() => setViewMode('grid')} title="Tarjetas">
            <Grid3X3 size={12} />
          </button>
          <button aria-label="Lista" type="button" aria-pressed={viewMode === 'list'} onClick={() => setViewMode('list')} title="Lista">
            <List size={12} />
          </button>
        </div>
      </div>

      {/* Tag chips */}
      {allTags.length > 0 && (
        <div className="ds-row-wrap">
          {allTags.map(t => (
            <button key={t} onClick={() => toggleTag(t)}
              className={`ds-pill${activeTags.includes(t) ? ' ds-pill--accent' : ''}`}
              style={{ cursor: 'pointer', fontFamily: 'inherit' }}>
              #{t}
            </button>
          ))}
          {activeTags.length > 0 && (
            <button onClick={() => setActiveTags([])}
              className="ds-pill ds-pill--danger"
              style={{ cursor: 'pointer', fontFamily: 'inherit' }}>
              Limpiar
            </button>
          )}
        </div>
      )}

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
          padding: '8px 14px',
          background: 'var(--accent-muted)', border: '1px solid var(--accent-border)',
          borderRadius: 'var(--radius-md)',
        }}>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--accent)', fontWeight: 600 }}>
            {selectedIds.size} seleccionado(s)
          </span>
          <Button size="sm" variant="danger"
            disabled={bulkDeleteMutation.isPending}
            onClick={() => { openConfirmGlobal({ message: `¿Eliminar ${selectedIds.size} documento(s)?`, onConfirm: () => bulkDeleteMutation.mutate(), danger: true }) }}>
            <Trash2 size={12} /> Eliminar seleccionados
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setSelectedIds(new Set())}>
            Cancelar
          </Button>
        </div>
      )}

      {/* Count */}
      <div className="ds-muted u-sm">
        {isLoading ? 'Cargando...' : `${docs.length} documento${docs.length !== 1 ? 's' : ''}${(search || filterCat || filterStatus || activeTags.length) ? ' (filtrado)' : ''}`}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="ds-grid-cards">
          {[...Array(8)].map((_, i) => (
            <div key={i} style={{ height: 190, background: 'var(--surface-2)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--surface-4)', opacity: 0.5 }} />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <div className="ds-empty">
          <FolderOpen size={36} className="ds-empty__icon" />
          <div className="ds-empty__title">{t('documents.no_documents')}</div>
          <div className="ds-empty__desc">
            {search || filterCat ? 'No hay resultados para los filtros aplicados.' : 'Sube tu primer documento con el botón “Nuevo documento”.'}
          </div>
          {!search && !filterCat && (
            <div style={{ marginTop: 'var(--space-3)' }}>
              <Button onClick={() => setShowUpload(true)}>
                <Upload size={14} /> Subir primer documento
              </Button>
            </div>
          )}
        </div>
      ) : viewMode === 'grid' ? (
        <div className="ds-grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(228px, 1fr))' }}>
          {docs.map(doc => (
            <DocCard key={doc.id} doc={doc}
              onView={setDrawerDocId}
              onDelete={d => { openConfirmGlobal({ message: `¿Eliminar "${d.title}"?`, onConfirm: () => deleteMutation.mutate(d.id), danger: true }) }}
              onSummary={summaryMutation.mutate}
              selected={selectedIds.has(doc.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      ) : (
        <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="u-table">
            <thead>
              <tr style={{ backgroundColor: 'var(--surface-3)', borderBottom: '1px solid var(--surface-4)' }}>
                <th style={{ padding: '10px 14px', width: 36 }}>
                  <button type="button" onClick={selectAll}
                    style={{ width: 16, height: 16, borderRadius: 4, border: `2px solid ${selectedIds.size === docs.length && docs.length > 0 ? 'var(--accent)' : 'var(--surface-5)'}`, backgroundColor: selectedIds.size === docs.length && docs.length > 0 ? 'var(--accent)' : 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {selectedIds.size === docs.length && docs.length > 0 && <Check size={9} color="white" strokeWidth={3} />}
                  </button>
                </th>
                <th style={{ padding: '10px 6px', width: 40 }} />
                {['Documento', 'Categoría', 'Aprobación', 'Tamaño', 'Fecha', 'Autor', ''].map(h => (
                  <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <DocRow key={doc.id} doc={doc}
                  onView={setDrawerDocId}
                  onDelete={d => { openConfirmGlobal({ message: `¿Eliminar "${d.title}"?`, onConfirm: () => deleteMutation.mutate(d.id), danger: true }) }}
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
