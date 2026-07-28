/**
 * DocumentsPanel  Panel embebible de documentos rediseV3ado 
 * Integra el sistema visual de Contecflow. Props: projectId?, taskId?, ticketId?, compact?
 */
import _React, { useState, useRef, useCallback } from 'react';
import { openConfirmGlobal } from '../context/ConfirmContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { documentsApi } from '../services/api';
import { useToast } from '../context/ToastContext';
import { extractErr } from '../utils/helpers';
import { Upload, Download, Trash2, Plus, Sparkles, Loader, X } from 'lucide-react';
import { useAppT } from '../hooks/useAppT';

import type { CSSProperties, DragEvent } from 'react';

function fmtBytes(b: number | null | undefined) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

const FILE_COLORS = {
  pdf:         { c: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 9%, transparent)',  l: 'PDF' },
  image:       { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 9%, transparent)',  l: 'IMG' },
  spreadsheet: { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 9%, transparent)', l: 'XLS' },
  word:        { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 9%, transparent)',  l: 'DOC' },
  presentation:{ c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 9%, transparent)', l: 'PPT' },
  other:       { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)',   l: 'FILE' },
};

function detectType(mime: string | null | undefined, name: string | null | undefined): keyof typeof FILE_COLORS {
  const ext = (name || '').split('.').pop()?.toLowerCase() ?? '';
  if (mime?.startsWith('image/')) return 'image';
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (mime?.includes('spreadsheet') || mime?.includes('excel') || ['xls','xlsx','csv'].includes(ext)) return 'spreadsheet';
  if (mime?.includes('word') || ['doc','docx'].includes(ext)) return 'word';
  if (mime?.includes('presentation') || ['ppt','pptx'].includes(ext)) return 'presentation';
  return 'other';
}

function FileIcon({ mime, name, size = 30 }: { mime?: string | null; name?: string | null; size?: number }) {
  const ft = FILE_COLORS[detectType(mime, name)];
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.25),
      backgroundColor: ft.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      fontFamily: 'var(--font-mono)', fontSize: Math.round(size * 0.24),
      fontWeight: 700, color: ft.c, letterSpacing: '-0.03em',
    }}>
      {ft.l}
    </div>
  );
}

const APPROVAL_ICON: Record<string, { c: string; icon: string }> = {
  approved: { c: 'var(--success)', icon: '✓' },
  rejected: { c: 'var(--danger)', icon: '✕' },
  pending:  { c: 'var(--warning)', icon: '◷' },
};

const CATS = ['contract','deliverable','proposal','sop','legal','requirements','meeting_notes','other'];

type IdVal = string | number | null | undefined;

function resolveQueryKey(projectId: IdVal, taskId: IdVal, ticketId: IdVal): (string | number | null | undefined)[] {
  if (taskId) return ['docs-task', taskId];
  if (ticketId) return ['docs-ticket', ticketId];
  return ['docs-project', projectId];
}

function resolveApiFn(projectId: IdVal, taskId: IdVal, ticketId: IdVal) {
  if (taskId) return () => documentsApi.byTask(taskId, {});
  if (ticketId) return () => documentsApi.byTicket(ticketId, {});
  return () => documentsApi.byProject(projectId, {});
}

interface DocVersion {
  file_mime_type?: string | null;
  file_name?: string | null;
  file_size?: number | null;
  download_url?: string | null;
}
interface Doc {
  id: string | number;
  title?: string;
  category?: string;
  latest_version?: DocVersion | null;
  requires_approval?: boolean;
  approval_status?: string | null;
}
interface DocumentsPanelProps {
  projectId?: IdVal;
  taskId?: IdVal;
  ticketId?: IdVal;
  _compact?: boolean;
}

export default function DocumentsPanel({ projectId, taskId, ticketId, _compact = false }: DocumentsPanelProps) {
  const { t } = useAppT();
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('other');
  const [dragOver, setDragOver] = useState(false);

  const qKey = resolveQueryKey(projectId, taskId, ticketId);
  const apiFn = resolveApiFn(projectId, taskId, ticketId);

  const { data: docs = [], isLoading } = useQuery<Doc[]>({
    queryKey: qKey,
    queryFn: async () => {
      const r = await apiFn();
      const d = r.data as { items?: Doc[] } | Doc[] | undefined;
      if (Array.isArray(d)) return d;
      return d?.items ?? [];
    },
    enabled: !!(projectId || taskId || ticketId),
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file as File);
      fd.append('title', title || (file as File).name);
      fd.append('category', category);
      if (projectId) fd.append('project_id', String(projectId));
      if (taskId)    fd.append('task_id',    String(taskId));
      if (ticketId)  fd.append('ticket_id',  String(ticketId));
      return documentsApi.upload(fd as unknown as Record<string, unknown>);
    },
    onSuccess: () => {
      toast.success(t('documents_panel.uploaded_ok'));
      qc.invalidateQueries({ queryKey: qKey });
      setFile(null); setTitle(''); setShowForm(false);
    },
    onError: e => toast.error(extractErr(e, t('documents_panel.upload_error'))),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string | number) => documentsApi.delete(id),
    onSuccess: () => { toast.success(t('documents_panel.deleted_ok')); qc.invalidateQueries({ queryKey: qKey }); },
    onError: e => toast.error(extractErr(e, t('documents_panel.delete_error'))),
  });

  const summaryMutation = useMutation({
    mutationFn: (id: string | number) => documentsApi.aiSummary(id),
    onSuccess: () => { toast.success(t('documents_panel.ai_summary_saved')); qc.invalidateQueries({ queryKey: qKey }); },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  });

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); setShowForm(true); }
  }, []);

  const fs: CSSProperties = { width: '100%', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 10px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };

  return (
    <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden', backgroundColor: 'var(--surface-1)' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 14px', borderBottom: '1px solid var(--surface-4)', backgroundColor: 'var(--surface-2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: 'color-mix(in srgb, var(--accent) 9%, transparent)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>
            Documentos
            {!isLoading && <span style={{ fontSize: "var(--text-xs)", fontWeight: 400, color: 'var(--text-3)', marginLeft: 5 }}>({docs.length})</span>}
          </span>
        </div>
        <button onClick={() => setShowForm(s => !s)}
          style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px', borderRadius: 7, border: 'none', backgroundColor: showForm ? 'var(--surface-3)' : 'var(--accent)', color: showForm ? 'var(--text-2)' : 'white', fontSize: "var(--text-xs)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
          {showForm ? <><X size={11} /> {t('documents_panel.close')}</> : <><Plus size={11} /> {t('documents_panel.add')}</>}
        </button>
      </div>

      {/* Upload form */}
      {showForm && (
        <div role="presentation"
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          style={{ padding: 12, borderBottom: '1px solid var(--surface-4)', backgroundColor: 'var(--surface-2)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button type="button" onClick={() => fileRef.current?.click()}
            style={{ border: `2px dashed ${dragOver || file ? 'var(--accent)' : 'var(--surface-5)'}`, borderRadius: 8, padding: '12px 10px', textAlign: 'center', cursor: 'pointer', transition: 'border-color 0.15s' }}>
            <input ref={fileRef} type="file" style={{ display: 'none' }}
              onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); } }} />
            {file
              ? <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{file.name}</span>
              : <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                  <Upload size={12} style={{ display: 'inline', marginRight: 4 }} />{t('documents_panel.click_or_drag')}
                </span>}
          </button>
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
              style={{ flex: 1, padding: '7px', borderRadius: 7, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
              {uploadMutation.isPending ? <Loader size={12} style={{ animation: 'spin 0.8s linear infinite' }} /> : <Upload size={12} />}
              {uploadMutation.isPending ? t('documents_panel.uploading') : t('documents_panel.upload')}
            </button>
            <button onClick={() => { setShowForm(false); setFile(null); setTitle(''); }}
              style={{ padding: '7px 12px', borderRadius: 7, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
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
          <div style={{ padding: '20px 14px', textAlign: 'center', fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            {t('documents_panel.no_documents')}
          </div>
        ) : (
          docs.map((doc, i) => {
            const lv = doc.latest_version;
            const approval = doc.requires_approval ? APPROVAL_ICON[doc.approval_status || 'pending'] : null;
            return (
              <div key={doc.id}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', borderBottom: i < docs.length - 1 ? '1px solid var(--surface-4)' : 'none' }}>
                <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', display: 'flex', gap: 6, alignItems: 'center', marginTop: 1 }}>
                    <span>{doc.category}</span>
                    {lv && <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtBytes(lv.file_size)}</span>}
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
