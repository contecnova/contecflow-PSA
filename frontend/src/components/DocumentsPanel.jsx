/**
 * DocumentsPanel  Panel embebible de documentos rediseV3ado 
 * Integra el sistema visual de Clarive. Props: projectId?, taskId?, ticketId?, compact?
 */
import _React, { useState, useRef, useCallback } from 'react';
import { openConfirmGlobal } from '../context/ConfirmContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { useToast } from '../context/ToastContext';
import { extractErr } from '../utils/helpers';
import { Upload, Download, Trash2, Plus, Sparkles, Loader, X } from 'lucide-react';
import { useAppT } from '../i18n/AppLangContext';

function fmtBytes(b) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

const FILE_COLORS = {
  pdf: { c: '#ef4444', bg: '#ef444418', l: 'PDF' },
  image: { c: '#3b82f6', bg: '#3b82f618', l: 'IMG' },
  spreadsheet: { c: '#10b981', bg: '#10b98118', l: 'XLS' },
  word: { c: '#6366f1', bg: '#6366f118', l: 'DOC' },
  presentation: { c: '#f59e0b', bg: '#f59e0b18', l: 'PPT' },
  other: { c: '#6b7280', bg: '#6b728018', l: 'FILE' },
};

function detectType(mime, name) {
  const ext = (name || '').split('.').pop()?.toLowerCase();
  if (mime?.startsWith('image/')) return 'image';
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (mime?.includes('spreadsheet') || mime?.includes('excel') || ['xls','xlsx','csv'].includes(ext)) return 'spreadsheet';
  if (mime?.includes('word') || ['doc','docx'].includes(ext)) return 'word';
  if (mime?.includes('presentation') || ['ppt','pptx'].includes(ext)) return 'presentation';
  return 'other';
}

function FileIcon({ mime, name, size = 30 }) {
  const ft = FILE_COLORS[detectType(mime, name)];
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.25),
      backgroundColor: ft.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      fontFamily: "'Space Mono', monospace", fontSize: Math.round(size * 0.24),
      fontWeight: 700, color: ft.c, letterSpacing: '-0.03em',
    }}>
      {ft.l}
    </div>
  );
}

const APPROVAL_ICON = {
  approved: { c: '#10b981', icon: '✓' },
  rejected: { c: '#ef4444', icon: '✕' },
  pending:  { c: '#f59e0b', icon: '◷' },
};

const CATS = ['contract','deliverable','proposal','sop','legal','requirements','meeting_notes','other'];

function resolveQueryKey(projectId, taskId, ticketId) {
  if (taskId) return ['docs-task', taskId];
  if (ticketId) return ['docs-ticket', ticketId];
  return ['docs-project', projectId];
}

function resolveApiPath(projectId, taskId, ticketId) {
  if (taskId) return `/documents/by-task/${taskId}`;
  if (ticketId) return `/documents/by-ticket/${ticketId}`;
  return `/documents/by-project/${projectId}`;
}

export default function DocumentsPanel({ projectId, taskId, ticketId, _compact = false }) {
  const t = useAppT();
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef();
  const [showForm, setShowForm] = useState(false);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('other');
  const [dragOver, setDragOver] = useState(false);

  const qKey = resolveQueryKey(projectId, taskId, ticketId);
  const apiPath = resolveApiPath(projectId, taskId, ticketId);

  const { data: docs = [], isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => api.get(apiPath).then(r => r.data),
    enabled: !!(projectId || taskId || ticketId),
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', title || file.name);
      fd.append('category', category);
      if (projectId) fd.append('project_id', String(projectId));
      if (taskId)    fd.append('task_id',    String(taskId));
      if (ticketId)  fd.append('ticket_id',  String(ticketId));
      return api.post('/documents/upload', fd);
    },
    onSuccess: () => {
      toast.success(t('documents_panel.uploaded_ok'));
      qc.invalidateQueries({ queryKey: qKey });
      setFile(null); setTitle(''); setShowForm(false);
    },
    onError: e => toast.error(extractErr(e, t('documents_panel.upload_error'))),
  });

  const deleteMutation = useMutation({
    mutationFn: id => api.delete(`/documents/${id}`),
    onSuccess: () => { toast.success(t('documents_panel.deleted_ok')); qc.invalidateQueries({ queryKey: qKey }); },
    onError: e => toast.error(extractErr(e, t('documents_panel.delete_error'))),
  });

  const summaryMutation = useMutation({
    mutationFn: id => api.post(`/documents/${id}/ai-summary`),
    onSuccess: () => { toast.success(t('documents_panel.ai_summary_saved')); qc.invalidateQueries({ queryKey: qKey }); },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  });

  const onDrop = useCallback(e => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); setShowForm(true); }
  }, []);

  const fs = { width: '100%', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 10px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };

  return (
    <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden', backgroundColor: 'var(--surface-1)' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 14px', borderBottom: '1px solid var(--surface-4)', backgroundColor: 'var(--surface-2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: '#3b82f618', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>
            Documentos
            {!isLoading && <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-3)', marginLeft: 5 }}>({docs.length})</span>}
          </span>
        </div>
        <button onClick={() => setShowForm(s => !s)}
          style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px', borderRadius: 7, border: 'none', backgroundColor: showForm ? 'var(--surface-3)' : 'var(--accent)', color: showForm ? 'var(--text-2)' : 'white', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
          {showForm ? <><X size={11} /> {t('documents_panel.close')}</> : <><Plus size={11} /> {t('documents_panel.add')}</>}
        </button>
      </div>

      {/* Upload form */}
      {showForm && (
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          style={{ padding: 12, borderBottom: '1px solid var(--surface-4)', backgroundColor: 'var(--surface-2)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div onClick={() => fileRef.current?.click()}
            style={{ border: `2px dashed ${dragOver || file ? 'var(--accent)' : 'var(--surface-5)'}`, borderRadius: 8, padding: '12px 10px', textAlign: 'center', cursor: 'pointer', transition: 'border-color 0.15s' }}>
            <input ref={fileRef} type="file" style={{ display: 'none' }}
              onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); } }} />
            {file
              ? <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{file.name}</span>
              : <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  <Upload size={12} style={{ display: 'inline', marginRight: 4 }} />{t('documents_panel.click_or_drag')}
                </span>}
          </div>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder={t('documents_panel.title_placeholder')}
            style={fs}
          />
          <select value={category} onChange={e => setCategory(e.target.value)} style={fs}>
            {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
          </select>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
              style={{ flex: 1, padding: '7px', borderRadius: 7, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: 12, fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
              {uploadMutation.isPending ? <Loader size={12} style={{ animation: 'spin 0.8s linear infinite' }} /> : <Upload size={12} />}
              {uploadMutation.isPending ? t('documents_panel.uploading') : t('documents_panel.upload')}
            </button>
            <button onClick={() => { setShowForm(false); setFile(null); setTitle(''); }}
              style={{ padding: '7px 12px', borderRadius: 7, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Document list */}
      <div>
        {isLoading ? (
          <div style={{ padding: '20px 14px', textAlign: 'center' }}>
            <Loader size={16} style={{ animation: 'spin 0.8s linear infinite', color: 'var(--text-3)' }} />
          </div>
        ) : docs.length === 0 ? (
          <div style={{ padding: '20px 14px', textAlign: 'center', fontSize: 12, color: 'var(--text-3)' }}>
            {t('documents_panel.no_documents')}
          </div>
        ) : (
          docs.map((doc, i) => {
            const lv = doc.latest_version;
            const approval = doc.requires_approval ? APPROVAL_ICON[doc.approval_status || 'pending'] : null;
            return (
              <div key={doc.id}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', borderBottom: i < docs.length - 1 ? '1px solid var(--surface-4)' : 'none', transition: 'background 0.1s' }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-2)'}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}>
                <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-3)', display: 'flex', gap: 6, alignItems: 'center', marginTop: 1 }}>
                    <span>{doc.category}</span>
                    {lv && <span style={{ fontFamily: "'Space Mono', monospace" }}>{fmtBytes(lv.file_size)}</span>}
                    {approval && <span style={{ color: approval.c, fontWeight: 700 }}>{approval.icon}</span>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 3, flexShrink: 0 }}>
                  {lv?.download_url && (
                    <a href={lv.download_url} target="_blank" rel="noreferrer" title={t('documents_panel.download_title')}
                      style={{ width: 24, height: 24, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none' }}>
                      <Download size={11} />
                    </a>
                  )}
                  <button onClick={() => summaryMutation.mutate(doc.id)} title={t('documents_panel.ai_summary_title')}
                    style={{ width: 24, height: 24, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--purple)' }}>
                    <Sparkles size={11} />
                  </button>
                  <button onClick={() => { openConfirmGlobal({message:`${t('documents_panel.delete_confirm')} "${doc.title}"?`,onConfirm:()=>deleteMutation.mutate(doc.id),danger:true}) }} title={t('documents_panel.delete_title')}
                    style={{ width: 24, height: 24, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
