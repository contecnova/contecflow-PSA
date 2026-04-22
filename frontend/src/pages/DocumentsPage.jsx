/**
 * DocumentsPage — Rediseño completo del hub de gestión documental
 * Diseo integrado con el sistema visual de Clarive (surface vars, accent, etc.)
 * Funcionalidades: KPIs, grid/tabla, drawer de detalle, carga modal dos columnas,
 * acciones bulk, etiquetas, aprobaciones, historial de versiones, resmenes IA
 */
import _React, { useState, useRef, useCallback, useMemo } from 'react';
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { useToast } from '../context/ToastContext';
import { useAppT } from '../i18n/AppLangContext'
import {
  Upload, Search, Grid3X3, List, Plus, Download, Trash2,
  Sparkles, History, X, Check, FolderOpen, Files, FileCheck,
  FileClock, TrendingUp, Eye, Info,
  CheckCircle, XCircle, ExternalLink, Loader
} from 'lucide-react';

// ── Utilidades ─────────────────────────────────────────
function fmtBytes(b) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}

function relTime(d) {
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

const FILE_COLORS = {
  pdf:          { c: '#ef4444', bg: '#ef444418', label: 'PDF' },
  image:        { c: '#3b82f6', bg: '#3b82f618', label: 'IMG' },
  spreadsheet:  { c: '#10b981', bg: '#10b98118', label: 'XLS' },
  word:         { c: '#6366f1', bg: '#6366f118', label: 'DOC' },
  presentation: { c: '#f59e0b', bg: '#f59e0b18', label: 'PPT' },
  archive:      { c: '#8b5cf6', bg: '#8b5cf618', label: 'ZIP' },
  text:         { c: '#64748b', bg: '#64748b18', label: 'TXT' },
  other:        { c: '#6b7280', bg: '#6b728018', label: 'FILE' },
};

function detectFileType(mime, name) {
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

function FileIcon({ mime, name, size = 36 }) {
  const type = detectFileType(mime, name);
  const ft = FILE_COLORS[type];
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.22),
      backgroundColor: ft.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      fontFamily: "'Space Mono', monospace", fontSize: Math.round(size * 0.23),
      fontWeight: 700, color: ft.c, letterSpacing: '-0.03em',
    }}>
      {ft.label}
    </div>
  );
}

const CAT_STYLE = {
  contract:     { c: '#3b82f6', bg: '#3b82f615' },
  deliverable:  { c: '#10b981', bg: '#10b98115' },
  proposal:     { c: '#8b5cf6', bg: '#8b5cf615' },
  sop:          { c: '#f59e0b', bg: '#f59e0b15' },
  legal:        { c: '#ef4444', bg: '#ef444415' },
  requirements: { c: '#06b6d4', bg: '#06b6d415' },
  report:       { c: '#f97316', bg: '#f9731615' },
  presentation: { c: '#ec4899', bg: '#ec489915' },
  other:        { c: '#6b7280', bg: '#6b728015' },
};

const APPROVAL_STYLE = {
  approved: { c: '#10b981', bg: '#10b98115', icon: '\u2713', label: 'Aprobado' },
  rejected: { c: '#ef4444', bg: '#ef444415', icon: '\u2715', label: 'Rechazado' },
  pending:  { c: '#f59e0b', bg: '#f59e0b15', icon: '\u25f7', label: 'Pendiente' },
};

function Chip({ text, color, bg }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
      backgroundColor: bg, color, textTransform: 'uppercase', letterSpacing: '0.04em',
      whiteSpace: 'nowrap',
    }}>
      {text}
    </span>
  );
}

// ── KPI card ─────────────────────────────────────────

function KpiCard({ icon: Icon, label, value, color, sub }) {
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 11, flexShrink: 0,
        backgroundColor: color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', fontFamily: "'Space Mono', monospace", lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 1 }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── Doc Card (Grid) ─────────────────────────────────────────

function DocCard({ doc, onView, onDelete, onSummary, selected, onToggleSelect }) {
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
      <div
        onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }}
        style={{
          position: 'absolute', top: 10, left: 10, zIndex: 2,
          width: 17, height: 17, borderRadius: 5,
          border: `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}`,
          backgroundColor: selected ? 'var(--accent)' : 'var(--surface-1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'all 0.12s', opacity: selected || hover ? 1 : 0,
        }}>
        {selected && <Check size={9} color="white" strokeWidth={3} />}
      </div>

      {/* Body */}
      <div style={{ padding: '14px 14px 10px', flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={42} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 13, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.35,
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
            }}>{doc.title}</div>
            {lv?.file_name && (
              <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2, fontFamily: "'Space Mono', monospace", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
              display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 600,
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
              <span key={t} style={{ fontSize: 10, padding: '1px 6px', borderRadius: 10, backgroundColor: 'var(--surface-3)', color: 'var(--text-3)' }}>
                #{t}
              </span>
            ))}
            {doc.tags.length > 3 && <span style={{ fontSize: 10, color: 'var(--text-3)' }}>+{doc.tags.length - 3}</span>}
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: '8px 14px 10px', borderTop: '1px solid var(--surface-4)',
        backgroundColor: 'var(--surface-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{relTime(doc.created_at)}</div>
          {lv && <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: "'Space Mono', monospace" }}>{fmtBytes(lv.file_size)}</div>}
        </div>
        <div style={{ display: 'flex', gap: 3, opacity: hover ? 1 : 0, transition: 'opacity 0.15s' }}
          onClick={e => e.stopPropagation()}>
          {lv?.download_url && (
            <a href={lv.download_url} target="_blank" rel="noreferrer" title="Descargar documento"
              style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none' }}>
              <Download size={11} />
            </a>
          )}
          <button onClick={() => onSummary(doc.id)} title="Generar resumen IA"
            style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--purple)' }}>
            <Sparkles size={11} />
          </button>
          <button onClick={() => onDelete(doc)} title="Eliminar documento"
            style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
            <Trash2 size={11} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Doc Row (Table) ─────────────────────────────────────────

function DocRow({ doc, onView, onDelete, onSummary, selected, onToggleSelect }) {
  const [hover, setHover] = useState(false);
  const lv = doc.latest_version;
  const catS = CAT_STYLE[doc.category] || CAT_STYLE.other;

  return (
    <tr
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onView(doc.id)}
      style={{
        backgroundColor: selected ? '#4f8ef710' : hover ? 'var(--surface-2)' : 'transparent',
        cursor: 'pointer', transition: 'background 0.1s',
        borderBottom: '1px solid var(--surface-4)',
      }}>
      <td style={{ padding: '10px 14px', width: 36 }} onClick={e => { e.stopPropagation(); onToggleSelect(doc.id); }}>
        <div style={{
          width: 16, height: 16, borderRadius: 4,
          border: `2px solid ${selected ? 'var(--accent)' : 'var(--surface-5)'}`,
          backgroundColor: selected ? 'var(--accent)' : 'transparent',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {selected && <Check size={9} color="white" strokeWidth={3} />}
        </div>
      </td>
      <td style={{ padding: '10px 6px', width: 38 }}>
        <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
      </td>
      <td style={{ padding: '10px 12px', maxWidth: 280 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
        {lv?.file_name && <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: "'Space Mono', monospace", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{lv.file_name}</div>}
      </td>
      <td style={{ padding: '10px 12px' }}>
        <Chip text={doc.category} color={catS.c} bg={catS.bg} />
      </td>
      <td style={{ padding: '10px 12px' }}>
        {doc.requires_approval ? (() => {
          const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
          return <Chip text={`${a.icon} ${a.label}`} color={a.c} bg={a.bg} />;
        })() : <span style={{ color: 'var(--text-3)', fontSize: 11 }}>—</span>}
      </td>
      <td style={{ padding: '10px 12px', fontSize: 11, color: 'var(--text-3)', fontFamily: "'Space Mono', monospace", whiteSpace: 'nowrap' }}>
        {lv ? fmtBytes(lv.file_size) : '—'}
      </td>
      <td style={{ padding: '10px 12px', fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{fmtDate(doc.created_at)}</td>
      <td style={{ padding: '10px 12px', fontSize: 11, color: 'var(--text-2)' }}>{doc.created_by_name || '—'}</td>
      <td style={{ padding: '10px 12px', width: 90 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', gap: 3, opacity: hover ? 1 : 0, transition: 'opacity 0.1s' }}>
          {lv?.download_url && (
            <a href={lv.download_url} target="_blank" rel="noreferrer"
              style={{ width: 24, height: 24, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none' }}>
              <Download size={11} />
            </a>
          )}
          <button onClick={() => onSummary(doc.id)}
            style={{ width: 24, height: 24, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--purple)' }}>
            <Sparkles size={11} />
          </button>
          <button onClick={() => onDelete(doc)}
            style={{ width: 24, height: 24, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
            <Trash2 size={11} />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Upload Modal ─────────────────────────────────────────

const CATS = ['contract','deliverable','proposal','sop','legal','requirements','report','presentation','other'];

function UploadModal({ open, onClose, onSuccess }) {
  const toast = useToast();
  const fileRef = useRef();
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState({ title:'', description:'', category:'other', tags:'', requires_approval: false, project_id:'' });

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-minimal'],
    queryFn: () => api.get('/projects').then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
    staleTime: 30000,
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', form.title || file.name);
      if (form.description) fd.append('description', form.description);
      fd.append('category', form.category);
      if (form.tags) fd.append('tags', form.tags);
      fd.append('requires_approval', String(form.requires_approval));
      if (form.project_id) fd.append('project_id', form.project_id);
      return api.post('/documents/upload', fd);
    },
    onSuccess: () => { toast.success('Documento subido correctamente'); onSuccess(); },
    onError: e => toast.error(e.response?.data?.detail
      ? (Array.isArray(e.response.data.detail)
          ? e.response.data.detail.map(d => d.msg).join(' · ')
          : e.response.data.detail)
      : 'Error al subir'),
  });

  const onDrop = useCallback(e => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); }
  }, []);

  const pickFile = f => { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); };

  if (!open) return null;

  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 };
  const fileType = file ? detectFileType(undefined, file.name) : null;
  const fileFt = fileType ? FILE_COLORS[fileType] : null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, backgroundColor: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }} onClick={onClose}>
      <div style={{ background: 'var(--surface-1)', borderRadius: 16, width: '100%', maxWidth: 740, border: '1px solid var(--surface-4)', boxShadow: '0 24px 64px rgba(0,0,0,0.5)', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '18px 24px', borderBottom: '1px solid var(--surface-4)' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-1)' }}>Subir documento</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>Arrastra un archivo o haz clic para seleccionarlo</div>
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
              style={{
                border: `2px dashed ${dragOver ? 'var(--accent)' : file ? (fileFt?.c || '#10b981') : 'var(--surface-5)'}`,
                borderRadius: 12, padding: '28px 16px', textAlign: 'center', cursor: 'pointer',
                backgroundColor: dragOver ? 'var(--surface-2)' : 'transparent', transition: 'all 0.15s',
                minHeight: 220, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
              }}>
              <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f); }} />
              {file ? (
                <>
                  <FileIcon mime={undefined} name={file.name} size={56} />
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)', wordBreak: 'break-all', maxWidth: 200 }}>{file.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: "'Space Mono', monospace" }}>{fmtBytes(file.size)}</div>
                  <button onClick={e => { e.stopPropagation(); setFile(null); }}
                    style={{ fontSize: 11, color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 4 }}>
                    Cambiar archivo 
                  </button>
                </>
              ) : (
                <>
                  <div style={{ width: 56, height: 56, borderRadius: 14, backgroundColor: 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Upload size={22} style={{ color: 'var(--text-3)' }} />
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-2)' }}>Arrastra aqutu archivo</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>o haz clic para seleccionar</div>
                  <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 4 }}>PDF, Word, Excel, Imágenes — máx. 100 MB</div>
                </>
              )}
            </div>
          </div>

          {/* Derecha: metadatos */}
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 13 }}>
            <div>
              <label style={ls}>Título *</label>
              <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} style={fs} placeholder={file?.name || 'Título del documento'} />
            </div>
            <div>
              <label style={ls}>Descripción</label>
              <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={2} style={{ ...fs, resize: 'none' }} placeholder="Descripcion del documento" aria-label="Descripcion del documento" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={ls}>Categoría</label>
                <select value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} style={fs}>
                  {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
                </select>
              </div>
              <div>
                <label style={ls}>Proyecto</label>
                <select value={form.project_id} onChange={e => setForm(p => ({ ...p, project_id: e.target.value }))} style={fs}>
                  <option value="">Sin proyecto</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} - ` : ''}{p.name}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label style={ls}>Etiquetas</label>
              <input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} style={fs} placeholder="Etiquetas separadas por comas" aria-label="Etiquetas separadas por comas" />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={form.requires_approval} onChange={e => setForm(p => ({ ...p, requires_approval: e.target.checked }))}
                style={{ width: 15, height: 15, accentColor: 'var(--accent)' }} />
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Requiere aprobación antes de usar</span>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 24px', borderTop: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'flex-end', gap: 10, backgroundColor: 'var(--surface-2)' }}>
          <button onClick={onClose} style={{ padding: '9px 20px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
            Cancelar
          </button>
          <button onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
            style={{ padding: '9px 22px', borderRadius: 8, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: 13, fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 7 }}>
            {uploadMutation.isPending ? <><Loader size={14} style={{ animation: 'spin 0.8s linear infinite' }} /> Subiendo...</> : <><Upload size={14} /> Subir documento</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Document Drawer (panel lateral) ─────────────────────────────────────────

function DocumentDrawer({ documentId, onClose, onRefresh }) {
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef();
  const [tab, setTab] = useState('preview');  // preview | versions | meta
  const [file, setFile] = useState(null);
  const [changeNote, setChangeNote] = useState('');
  const [showUploadVersion, setShowUploadVersion] = useState(false);
  const [previewVersion, setPreviewVersion] = useState(null);
  const [isEditingMeta, setIsEditingMeta] = useState(false);
  const [metaForm, setMetaForm] = useState(null);

  const { data: doc, isLoading } = useQuery({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const res = await api.get(`/documents/${documentId}`);
      const d = res.data;
      if (d.versions) d.versions = d.versions.map(v => ({ ...v, download_url: v.download_url || v.s3_url }));
      return d;
    },
    onSuccess: d => { if (d.versions?.length && !previewVersion) setPreviewVersion(d.versions[0]); },
  });

  const approveMutation = useMutation({
    mutationFn: status => api.post(`/documents/${documentId}/approve`, { status }),
    onSuccess: (_, s) => { toast.success(s === 'approved' ? 'Documento aprobado' : 'Documento rechazado'); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: e => toast.error(e.response?.data?.detail || 'Error'),
  });

  const summaryMutation = useMutation({
    mutationFn: () => api.post(`/documents/${documentId}/ai-summary`),
    onSuccess: () => { toast.success('Resumen IA generado'); qc.invalidateQueries({ queryKey: ['document', documentId] }); },
    onError: e => toast.error(e.response?.data?.detail || 'Error IA'),
  });

  const versionMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file);
      if (changeNote) fd.append('change_note', changeNote);
      return api.post(`/documents/${documentId}/versions`, fd);
    },
    onSuccess: () => { toast.success('Nueva versión subida'); qc.invalidateQueries({ queryKey: ['document', documentId] }); setFile(null); setChangeNote(''); setShowUploadVersion(false); onRefresh(); },
    onError: e => toast.error(e.response?.data?.detail || 'Error'),
  });

  const updateMetaMutation = useMutation({
    mutationFn: data => api.patch(`/documents/${documentId}`, data),
    onSuccess: () => {
      toast.success('Metadatos actualizados');
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      qc.invalidateQueries({ queryKey: ['documents'] });
      setIsEditingMeta(false);
      onRefresh();
    },
    onError: e => toast.error(e.response?.data?.detail || 'Error al guardar'),
  });

  const activeVer = previewVersion || doc?.versions?.[0] || null;
  const catS = doc ? (CAT_STYLE[doc.category] || CAT_STYLE.other) : null;

  const tabBtnStyle = (id) => ({
    padding: '6px 14px', borderRadius: 7, border: `1px solid ${tab === id ? 'var(--accent)40' : 'var(--surface-4)'}`,
    backgroundColor: tab === id ? 'var(--accent)15' : 'transparent',
    color: tab === id ? 'var(--accent)' : 'var(--text-2)',
    fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.12s',
  });

  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };

  return (
    <>
      {/* Overlay */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 900, backgroundColor: 'rgba(0,0,0,0.35)' }} onClick={onClose} />

      {/* Drawer */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 901,
        width: 600, backgroundColor: 'var(--surface-1)',
        borderLeft: '1px solid var(--surface-4)',
        boxShadow: '-12px 0 48px rgba(0,0,0,0.3)',
        display: 'flex', flexDirection: 'column', overflowY: 'auto',
      }}>
        {isLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: 'var(--text-3)', fontSize: 13 }}>
            <Loader size={18} style={{ animation: 'spin 0.8s linear infinite', marginRight: 8 }} /> Cargando...
          </div>
        ) : !doc ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: 'var(--danger)', fontSize: 13 }}>Documento no encontrado</div>
        ) : (
          <>
            {/* Drawer header */}
            <div style={{ padding: '18px 22px 14px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    <FileIcon mime={activeVer?.file_mime_type} name={activeVer?.file_name} size={38} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h2 style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-1)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</h2>
                      {doc.description && <p style={{ fontSize: 12, color: 'var(--text-3)', margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.description}</p>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    <Chip text={doc.category} color={catS.c} bg={catS.bg} />
                    {doc.requires_approval && (() => {
                      const a = APPROVAL_STYLE[doc.approval_status || 'pending'];
                      return <Chip text={`${a.icon} ${a.label}`} color={a.c} bg={a.bg} />;
                    })()}
                    {doc.tags?.map(t => (
                      <span key={t} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 10, backgroundColor: 'var(--surface-3)', color: 'var(--text-3)' }}>#{t}</span>
                    ))}
                  </div>
                </div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4, flexShrink: 0 }}>
                  <X size={18} />
                </button>
              </div>

              {/* Action row */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {doc.requires_approval && doc.approval_status === 'pending' && (
                  <>
                    <button onClick={() => approveMutation.mutate('approved')} style={{ padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: '#10b981', color: 'white', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <CheckCircle size={13} /> Aprobar
                    </button>
                    <button onClick={() => approveMutation.mutate('rejected')} style={{ padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--danger)', color: 'white', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <XCircle size={13} /> Rechazar
                    </button>
                  </>
                )}
                <button onClick={() => summaryMutation.mutate()} disabled={summaryMutation.isPending}
                  style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--purple)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                   <Sparkles size={13} /> {summaryMutation.isPending ? 'Generando...' : 'Resumen IA'}
                </button>
                {activeVer?.download_url && (
                  <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                    style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 12, fontWeight: 700, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Download size={13} /> Descargar
                  </a>
                )}
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 6, padding: '12px 22px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
              <button style={tabBtnStyle('preview')} onClick={() => setTab('preview')}>
                <Eye size={12} style={{ display: 'inline', marginRight: 4 }} /> Vista previa
              </button>
              <button style={tabBtnStyle('versions')} onClick={() => setTab('versions')}>
                <History size={12} style={{ display: 'inline', marginRight: 4 }} />
                Versiones {doc.versions?.length > 0 && `(${doc.versions.length})`}
              </button>
              <button style={tabBtnStyle('meta')} onClick={() => setTab('meta')}>
                <Info size={12} style={{ display: 'inline', marginRight: 4 }} /> Metadatos
              </button>
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 22 }}>

              {/* Preview */}
              {tab === 'preview' && activeVer?.download_url && (
                <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
                  <div style={{ padding: '8px 14px', backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{activeVer.file_name} · {fmtBytes(activeVer.file_size)}</span>
                    <a href={activeVer.download_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
                       <ExternalLink size={11} /> Abrir en nueva pestaña
                    </a>
                  </div>
                  {(() => {
                    const type = detectFileType(activeVer.file_mime_type, activeVer.file_name);
                    if (type === 'pdf') return <iframe src={activeVer.download_url} style={{ width: '100%', height: 480, border: 'none' }} title="Vista previa del PDF" />;
                    if (type === 'image') return <img src={activeVer.download_url} alt={activeVer.file_name} style={{ maxWidth: '100%', maxHeight: 480, objectFit: 'contain', display: 'block', margin: '0 auto', padding: 16 }} />;
                    return (
                      <div style={{ padding: 40, textAlign: 'center' }}>
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div style={{ marginTop: 14, fontSize: 13, color: 'var(--text-3)' }}>Vista previa no disponible para este tipo de archivo</div>
                        <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 12, padding: '8px 16px', borderRadius: 8, backgroundColor: 'var(--accent)', color: 'white', textDecoration: 'none', fontSize: 13, fontWeight: 700 }}>
                          <Download size={14} /> Descargar para ver
                        </a>
                      </div>
                    );
                  })()}
                </div>
              )}
              {tab === 'preview' && !activeVer?.download_url && (
                <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-3)', fontSize: 13 }}>
                  <FolderOpen size={36} style={{ display: 'block', margin: '0 auto 12px', opacity: 0.4 }} />
                  Este documento no tiene archivo adjunto todavía.
                </div>
              )}

              {/* Versions */}
              {tab === 'versions' && (
                <div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                    {(doc.versions || []).map((v, i) => (
                      <div key={v.id}
                        onClick={() => { setPreviewVersion(v); setTab('preview'); }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
                          backgroundColor: activeVer?.id === v.id ? 'var(--surface-3)' : 'var(--surface-2)',
                          border: `1px solid ${activeVer?.id === v.id ? 'var(--accent)40' : 'var(--surface-4)'}`,
                          transition: 'all 0.12s',
                        }}>
                        <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: activeVer?.id === v.id ? 'var(--accent)' : 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Mono', monospace", fontSize: 11, fontWeight: 700, color: activeVer?.id === v.id ? 'white' : 'var(--text-2)', flexShrink: 0 }}>
                          v{v.version_num}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.file_name}</div>
                          {v.change_note && <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.change_note}</div>}
                          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{v.uploader_name} · {fmtDate(v.created_at)} · {fmtBytes(v.file_size)}</div>
                        </div>
                        {i === 0 && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10, backgroundColor: 'var(--accent)20', color: 'var(--accent)', fontWeight: 700 }}>Actual</span>}
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
                    <button onClick={() => setShowUploadVersion(true)}
                      style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: '1px dashed var(--surface-5)', backgroundColor: 'transparent', color: 'var(--accent)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', width: '100%', justifyContent: 'center' }}>
                      <Upload size={14} /> Subir nueva versión
                    </button>
                  ) : (
                    <div style={{ padding: 14, borderRadius: 10, border: '1px solid var(--surface-4)', backgroundColor: 'var(--surface-2)', display: 'flex', flexDirection: 'column', gap: 10 }}>
                      <div onClick={() => fileRef.current?.click()} style={{ border: `2px dashed ${file ? '#10b981' : 'var(--surface-5)'}`, borderRadius: 8, padding: '12px 16px', textAlign: 'center', cursor: 'pointer' }}>
                        {file ? <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{file.name}</span>
                          : <span style={{ fontSize: 12, color: 'var(--text-3)' }}><Upload size={13} style={{ display: 'inline', marginRight: 4 }} />Clic para seleccionar archivo</span>}
                        <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={e => setFile(e.target.files?.[0])} />
                      </div>
                      <input placeholder="Nota del cambio" value={changeNote} onChange={e => setChangeNote(e.target.value)} style={fs} aria-label="Nota del cambio" />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => versionMutation.mutate()} disabled={!file || versionMutation.isPending}
                          style={{ flex: 1, padding: '8px', borderRadius: 8, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: 13, fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit' }}>
                          {versionMutation.isPending ? 'Subiendo...' : 'Subir'}
                        </button>
                        <button onClick={() => { setShowUploadVersion(false); setFile(null); setChangeNote(''); }}
                          style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
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
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                    {[
                      ['Creado por', doc.created_by_name || '—'],
                      ['Fecha creación', fmtDate(doc.created_at)],
                      ['Categoría', doc.category],
                      ['Versiones', doc.versions?.length || 1],
                      ['Requiere aprob.', doc.requires_approval ? 'Sí' : 'No'],
                      ['Estado aprob.', doc.approval_status || '—'],
                      doc.approved_by_name && ['Aprobado por', doc.approved_by_name],
                      doc.approved_at && ['Fecha aprob.', fmtDate(doc.approved_at)],
                    ].filter(Boolean).map(([k, v]) => (
                      <div key={k} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>{k}</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{v}</div>
                      </div>
                    ))}
                    {doc.description && (
                      <div style={{ gridColumn: '1/-1', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>Descripción</div>
                        <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{doc.description}</div>
                      </div>
                    )}
                    {doc.tags?.length > 0 && (
                      <div style={{ gridColumn: '1/-1', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Etiquetas</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {doc.tags.map(t => (
                            <span key={t} style={{ fontSize: 12, padding: '3px 10px', borderRadius: 12, backgroundColor: 'var(--surface-3)', color: 'var(--text-2)' }}>#{t}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <button onClick={() => {
                    setMetaForm({ title: doc.title || '', description: doc.description || '', category: doc.category || 'other', requires_approval: doc.requires_approval ?? false });
                    setIsEditingMeta(true);
                  }} style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-1)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6 }}>
                    ✏️ Editar metadatos
                  </button>
                </div>
              )}

              {tab === 'meta' && isEditingMeta && metaForm && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>Título *</label>
                    <input value={metaForm.title} onChange={e => setMetaForm(f => ({ ...f, title: e.target.value }))} style={fs} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>Descripción</label>
                    <textarea value={metaForm.description} onChange={e => setMetaForm(f => ({ ...f, description: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical', lineHeight: 1.6 }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>Categoría</label>
                    <select value={metaForm.category} onChange={e => setMetaForm(f => ({ ...f, category: e.target.value }))} style={fs}>
                      <option value="contract">Contrato</option>
                      <option value="deliverable">Entregable</option>
                      <option value="proposal">Propuesta</option>
                      <option value="sop">Procedimiento (SOP)</option>
                      <option value="requirements">Requisitos</option>
                      <option value="meeting_notes">Notas de reunión</option>
                      <option value="legal">Legal</option>
                      <option value="other">Otro</option>
                    </select>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <input type="checkbox" id="meta-req-approval" checked={metaForm.requires_approval} onChange={e => setMetaForm(f => ({ ...f, requires_approval: e.target.checked }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                    <label htmlFor="meta-req-approval" style={{ fontSize: 13, color: 'var(--text-1)', cursor: 'pointer' }}>Requiere aprobación</label>
                  </div>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 6, borderTop: '1px solid var(--surface-4)' }}>
                    <button onClick={() => setIsEditingMeta(false)} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>Cancelar</button>
                    <button onClick={() => updateMetaMutation.mutate(metaForm)} disabled={updateMetaMutation.isPending || !metaForm.title}
                      style={{ padding: '7px 16px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'white', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                      {updateMetaMutation.isPending ? 'Guardando...' : '💾 Guardar'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}

// ── Página principal ────────────────────────────────────────────

const SORT_OPTS = [
  { v: 'date_desc', l: 'Más recientes' },
  { v: 'date_asc',  l: 'Más antiguos' },
  { v: 'name_asc',  l: 'A–Z' },
  { v: 'size_desc', l: 'Más grandes' },
];

export default function DocumentsPage() {
  const _t = useAppT()
  const toast = useToast();
  const qc = useQueryClient();
  const [viewMode, setViewMode] = useState('grid');
  const [search, setSearch] = useState('');
  const [filterCat, setFilterCat] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [sortBy, setSortBy] = useState('date_desc');
  const [activeTags, setActiveTags] = useState([]);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [drawerDocId, setDrawerDocId] = useState(null);

  const { data: docsRaw = [], isLoading } = useQuery({
    queryKey: ['documents', filterCat, filterStatus, search],
    queryFn: () => {
      const p = { limit: 200 };
      if (filterCat) p.category = filterCat;
      if (search) p.search = search;
      return api.get('/documents', { params: p }).then(r => Array.isArray(r.data) ? r.data : []);
    },
  });

  const docs = useMemo(() => {
    let d = [...docsRaw];
    if (filterStatus === 'pending') d = d.filter(x => x.requires_approval && (x.approval_status === 'pending' || !x.approval_status));
    else if (filterStatus === 'approved') d = d.filter(x => x.approval_status === 'approved');
    if (activeTags.length) d = d.filter(x => activeTags.every(t => x.tags?.includes(t)));
    if (sortBy === 'date_desc') d.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    else if (sortBy === 'date_asc') d.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    else if (sortBy === 'title_asc') d.sort((a, b) => a.title.localeCompare(b.title));
    else if (sortBy === 'size_desc') d.sort((a, b) => (b.latest_version?.file_size || 0) - (a.latest_version?.file_size || 0));
    return d;
  }, [docsRaw, filterStatus, activeTags, sortBy]);

  const stats = useMemo(() => {
    const weekAgo = Date.now() - 7 * 86400000;
    return {
      total: docsRaw.length,
      pending: docsRaw.filter(d => d.requires_approval && (d.approval_status === 'pending' || !d.approval_status)).length,
      approved: docsRaw.filter(d => d.approval_status === 'approved').length,
      thisWeek: docsRaw.filter(d => new Date(d.created_at).getTime() > weekAgo).length,
    };
  }, [docsRaw]);

  const allTags = useMemo(() => {
    const s = new Set();
    docsRaw.forEach(d => d.tags?.forEach(t => s.add(t)));
    return [...s].slice(0, 24);
  }, [docsRaw]);

  const deleteMutation = useMutation({
    mutationFn: id => api.delete(`/documents/${id}`),
    onSuccess: () => { toast.success('Documento eliminado'); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => toast.error('Error al eliminar'),
  });

  const summaryMutation = useMutation({
    mutationFn: id => api.post(`/documents/${id}/ai-summary`),
    onSuccess: () => { toast.success('Resumen IA generado'); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: e => toast.error(e.response?.data?.detail || 'Error IA'),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: () => Promise.all([...selectedIds].map(id => api.delete(`/documents/${id}`))),
    onSuccess: () => { toast.success(`${selectedIds.size} documento(s) eliminados`); setSelectedIds(new Set()); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => toast.error('Error en operación masiva'),
  });

  const toggleSelect = id => setSelectedIds(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleTag = t => setActiveTags(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t]);
  const selectAll = () => setSelectedIds(docs.length === selectedIds.size ? new Set() : new Set(docs.map(d => d.id)));

  const ctrlBtn = { padding: '8px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', outline: 'none' };

  return (
    <div style={{ padding: '24px 28px', maxWidth: 1440, margin: '0 auto' }}>

      {/* Page header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: '#3b82f620', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Files size={20} style={{ color: '#3b82f6' }} />
          </div>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', margin: 0 }}>Documentos</h1>
            <p style={{ fontSize: 12, color: 'var(--text-3)', margin: 0 }}>Gestión centralizada de archivos, contratos y documentación del proyecto.</p>
          </div>
        </div>
        <button onClick={() => setShowUpload(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '10px 18px', borderRadius: 10, border: 'none', backgroundColor: 'var(--accent)', color: 'white', fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
          <Plus size={16} /> Nuevo documento
        </button>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 22 }}>
        <KpiCard icon={Files}      label="Total documentos" value={stats.total} color="#3b82f6" sub="en la plataforma" />
        <KpiCard icon={FileClock}  label="Pendientes" value={stats.pending} color="#f59e0b" sub="requieren revision" />
        <KpiCard icon={FileCheck}  label="Aprobados" value={stats.approved} color="#10b981" sub="documentos validos" />
        <KpiCard icon={TrendingUp} label="Esta semana" value={stats.thisWeek} color="var(--purple)" sub="nuevos documentos" />
      </div>

      {/* Filter bar */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '12px 16px', marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 160 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', pointerEvents: 'none' }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar por titulo, archivo o etiqueta"
            style={{ width: '100%', paddingLeft: 30, paddingRight: 10, paddingTop: 8, paddingBottom: 8, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} />
        </div>
        <select value={filterCat} onChange={e => setFilterCat(e.target.value)} style={ctrlBtn}>
          <option value="">Todas las categors</option>
          {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={ctrlBtn}>
          <option value="">Todos los estados</option>
            <option value="pending">Pendiente aprobación</option>
          <option value="approved">Aprobados</option>
        </select>
        <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={ctrlBtn}>
          {SORT_OPTS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        {/* View toggle */}
        <div style={{ display: 'flex', gap: 2, background: 'var(--surface-3)', borderRadius: 8, padding: 3 }}>
          {[['grid', <Grid3X3 key="grid" size={14} />], ['list', <List key="list" size={14} />]].map(([m, icon]) => (
            <button key={m} onClick={() => setViewMode(m)}
              style={{ padding: '5px 10px', borderRadius: 6, border: 'none', cursor: 'pointer', backgroundColor: viewMode === m ? 'var(--accent)' : 'transparent', color: viewMode === m ? 'white' : 'var(--text-2)', transition: 'all 0.12s', display: 'flex', alignItems: 'center' }}>
              {icon}
            </button>
          ))}
        </div>
      </div>

      {/* Tag chips */}
      {allTags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 12 }}>
          {allTags.map(t => (
            <button key={t} onClick={() => toggleTag(t)}
              style={{ padding: '3px 10px', borderRadius: 20, border: `1px solid ${activeTags.includes(t) ? 'var(--accent)' : 'var(--surface-4)'}`, backgroundColor: activeTags.includes(t) ? 'var(--accent)15' : 'transparent', color: activeTags.includes(t) ? 'var(--accent)' : 'var(--text-3)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.12s' }}>
              #{t}
            </button>
          ))}
          {activeTags.length > 0 && (
            <button onClick={() => setActiveTags([])} style={{ padding: '3px 9px', borderRadius: 20, border: '1px solid var(--danger)40', backgroundColor: 'transparent', color: 'var(--danger)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
 Limpiar              
            </button>
          )}
        </div>
      )}

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', background: 'var(--surface-3)', border: '1px solid var(--accent)40', borderRadius: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: 600 }}>{selectedIds.size} seleccionado(s)</span>
            <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar ${selectedIds.size} documento(s)?`, onConfirm: () => bulkDeleteMutation.mutate(), danger: true }) }} disabled={bulkDeleteMutation.isPending}
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 14px', borderRadius: 7, border: 'none', backgroundColor: 'var(--danger)', color: 'white', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700 }}>
            <Trash2 size={12} /> Eliminar seleccionados
          </button>
          <button onClick={() => setSelectedIds(new Set())} style={{ padding: '5px 10px', borderRadius: 7, border: '1px solid var(--surface-5)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
            Cancelar
          </button>
        </div>
      )}

      {/* Count */}
      <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 14 }}>
        {isLoading ? 'Cargando...' : `${docs.length} documento${docs.length !== 1 ? 's' : ''}${(search || filterCat || filterStatus || activeTags.length) ? ' (filtrado)' : ''}`}
      </div>

      {/* Content */}
      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 16 }}>
          {[...Array(8)].map((_, i) => (
            <div key={i} style={{ height: 190, background: 'var(--surface-2)', borderRadius: 12, border: '1px solid var(--surface-4)', opacity: 0.5 }} />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '64px 24px', gap: 14 }}>
          <div style={{ width: 72, height: 72, borderRadius: 18, backgroundColor: 'var(--surface-2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <FolderOpen size={30} style={{ color: 'var(--text-3)' }} />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6 }}>Sin documentos</div>
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
              {search || filterCat ? 'No hay resultados para los filtros aplicados.' : 'Sube tu primer documento con el botón "Nuevo documento".'}
            </div>
          </div>
          {!search && !filterCat && (
            <button onClick={() => setShowUpload(true)}
              style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '10px 20px', borderRadius: 10, border: 'none', backgroundColor: 'var(--accent)', color: 'white', fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
              <Upload size={14} /> Subir primer documento
            </button>
          )}
        </div>
      ) : viewMode === 'grid' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(228px, 1fr))', gap: 14 }}>
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
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--surface-3)', borderBottom: '1px solid var(--surface-4)' }}>
                <th style={{ padding: '10px 14px', width: 36 }}>
                  <div onClick={selectAll}
                    style={{ width: 16, height: 16, borderRadius: 4, border: `2px solid ${selectedIds.size === docs.length && docs.length > 0 ? 'var(--accent)' : 'var(--surface-5)'}`, backgroundColor: selectedIds.size === docs.length && docs.length > 0 ? 'var(--accent)' : 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {selectedIds.size === docs.length && docs.length > 0 && <Check size={9} color="white" strokeWidth={3} />}
                  </div>
                </th>
                <th style={{ padding: '10px 6px', width: 40 }} />
                {['Documento', 'Categoría', 'Aprobación', 'Tamaño', 'Fecha', 'Autor', ''].map(h => (
                  <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
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
    </div>
  );
}
