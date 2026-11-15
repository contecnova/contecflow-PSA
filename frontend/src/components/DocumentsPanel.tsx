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

import type { DragEvent } from 'react';
import './DocumentsPanel.css'
import { useAppLang } from '../i18n/AppLangContext'

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
    <div className="docupane-row-8" style={{ width: size, height: size, borderRadius: Math.round(size * 0.25), backgroundColor: ft.bg, fontSize: Math.round(size * 0.24), color: ft.c }}>
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

interface DocumentsPanelProps {
  projectId?: IdVal;
  taskId?: IdVal;
  ticketId?: IdVal;
  _compact?: boolean;
}

export default function DocumentsPanel({ projectId, taskId, ticketId, _compact = false }: DocumentsPanelProps) {
  const { t: traducir } = useAppLang()
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

  const { data: docs = [], isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => apiFn().then(r => r.data),
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
      return documentsApi.upload(fd);
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


  return (
    <div className="docupane-box-1">

      {/* Header */}
      <div className="docupane-row-1">
        <div className="docupane-row-2">
          <div className="docupane-row-3">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <span className="docupane-txt-1">
            {traducir('docs.titulo')}
            {!isLoading && <span className="docupane-box-2">({docs.length})</span>}
          </span>
        </div>
        <button className="docupane-row-9" onClick={() => setShowForm(s => !s)}
          style={{ backgroundColor: showForm ? 'var(--surface-3)' : 'var(--accent)', color: showForm ? 'var(--text-2)' : 'white' }}>
          {showForm ? <><X size={11} /> {t('documents_panel.close')}</> : <><Plus size={11} /> {t('documents_panel.add')}</>}
        </button>
      </div>

      {/* Upload form */}
      {showForm && (
        <div role="presentation"
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className="docupane-stack-1">
          <button className="docupane-box-8 document-sx2" type="button" onClick={() => fileRef.current?.click()}
            style={{ border: `2px dashed ${dragOver || file ? 'var(--accent)' : 'var(--surface-5)'}` }}>
            <input ref={fileRef} type="file" aria-label={t('documents_panel.click_or_drag')} className="docupane-box-3"
              onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); } }} />
            {file
              ? <span className="u-text1-sm-600">{file.name}</span>
              : <span className="u-text3-xs">
                  <Upload size={12} className="document-sx3" />{t('documents_panel.click_or_drag')}
                </span>}
          </button>
          <input aria-label={t('documents_panel.title_placeholder')}
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder={t('documents_panel.title_placeholder')}
            className="docupane-fs"
          />
          <select value={category} onChange={e => setCategory(e.target.value)} className="docupane-fs">
            {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
          </select>
          <div className="u-row-6">
            <button className="docupane-row-10" onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
              style={{ backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', cursor: !file ? 'not-allowed' : 'pointer' }}>
              {uploadMutation.isPending ? <Loader size={12} className="document-sx4" /> : <Upload size={12} />}
              {uploadMutation.isPending ? t('documents_panel.uploading') : t('documents_panel.upload')}
            </button>
            <button onClick={() => { setShowForm(false); setFile(null); setTitle(''); }}
              className="docupane-box-4">
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Document list */}
      <div>
        {isLoading ? (
          <div className="docupane-box-5">
            <Loader size={16} className="document-sx5" />
          </div>
        ) : docs.length === 0 ? (
          <div className="docupane-box-6">
            {t('documents_panel.no_documents')}
          </div>
        ) : (
          docs.map((doc, i) => {
            const lv = doc.latest_version;
            const approval = doc.requires_approval ? APPROVAL_ICON[doc.approval_status || 'pending'] : null;
            return (
              <div className="docupane-row-11" key={doc.id}
                style={{ borderBottom: i < docs.length - 1 ? '1px solid var(--surface-4)' : 'none' }}>
                <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
                <div className="u-flex1-min0">
                  <div className="docupane-box-7">{doc.title}</div>
                  <div className="docupane-row-4">
                    <span>{doc.category}</span>
                    {lv && <span className="u-mono">{fmtBytes(lv.file_size)}</span>}
                    {approval && <span className="docupane-txt-2" style={{ color: approval.c }}>{approval.icon}</span>}
                  </div>
                </div>
                <div className="docupane-row-5">
                  {lv?.download_url && (
                    <a href={lv.download_url} target="_blank" rel="noreferrer" title={t('documents_panel.download_title')}
                      className="docupane-row-6">
                      <Download size={11} />
                    </a>
                  )}
                  <button aria-label={t('documents_panel.ai_summary_title')} onClick={() => summaryMutation.mutate(doc.id)} title={t('documents_panel.ai_summary_title')}
                    className="docupane-row-12">
                    <Sparkles size={11} />
                  </button>
                  <button aria-label={t('documents_panel.delete_title')} onClick={() => { openConfirmGlobal({message:`${t('documents_panel.delete_confirm')} "${doc.title}"?`,onConfirm:()=>deleteMutation.mutate(doc.id),danger:true}) }} title={t('documents_panel.delete_title')}
                    className="docupane-row-7">
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
