/**
 * DocumentsPage — Rediseño completo del hub de gestión documental
 * Diseo integrado con el sistema visual de Contecflow (surface vars, accent, etc.)
 * Funcionalidades: KPIs, grid/tabla, drawer de detalle, carga modal dos columnas,
 * acciones bulk, etiquetas, aprobaciones, historial de versiones, resmenes IA
 */
import { useState, useMemo, type CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { Search, Grid3X3, List, Plus, Trash2, Check, FolderOpen, Files, FileCheck, FileClock, FileMinus, TrendingUp } from 'lucide-react'
import { Buscador, Page, Button, KpiCard, EmptyState, Pulsable, Select, TablaSimple } from '../components/ui'
import { extractErr } from '../utils/helpers'
import { DOCUMENTS_LIST_LIMIT } from '../constants/pagination'
import { type DocListItem, etiquetaCategoria } from './documentos/compartido'
import { CATS, UploadModal } from './documentos/SubidaYCompartir'
import { DocCard, DocRow } from './documentos/TarjetasDeDocumento'
import { DocumentDrawer } from './documentos/CajonDeDocumento'
import './DocumentsPage.css'

// ── Página principal ────────────────────────────────────────────

const SORT_OPTS = [
  { v: 'date_desc', l: 'pagina_docs.mas_recientes' },
  { v: 'date_asc',  l: 'pagina_docs.mas_antiguos' },
  { v: 'name_asc',  l: 'pagina_docs.a_z' },
  { v: 'size_desc', l: 'pagina_docs.mas_grandes' },
];

export default function DocumentsPage(): JSX.Element {
  const t = useAppT()
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
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.error_ia'))),
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
      title={t('nav.documents')}
      subtitle={t('documents.subtitle')}
      rightActions={
        <Button icon={<Plus size={14} />} onClick={() => setShowUpload(true)}>
          {t('documents.upload')}
        </Button>
      }
    >
      {/* KPIs */}
      <div className="ds-grid-stats">
        <KpiCard icon={<Files size={16} />} label={t('pagina_docs.total_documentos')} value={stats.total} />
        <KpiCard icon={<FileClock size={16} />} label={t('pagina_docs.pendientes')} value={stats.pending} warning={stats.pending > 0} sub={t('pagina_docs.requieren_revision')} />
        <KpiCard icon={<FileCheck size={16} />} label={t('pagina_docs.aprobados')} value={stats.approved} />
        <KpiCard icon={<FileMinus size={16} />} label={t('documents.sin_aprobacion')} value={stats.noApproval} />
        <KpiCard icon={<TrendingUp size={16} />} label={t('documents.esta_semana')} value={stats.thisWeek} accent={stats.thisWeek > 0} />
      </div>

      {/* Filter bar — toolbar plana, sin caja contenedora (consistente con
          TasksPage / ProjectsPage / TicketListTab) */}
      <div className="ds-toolbar">
        <Buscador className="docs-box-36" value={search} onChange={setSearch} placeholder={t('documents.buscar_por_titulo_archivo_o_etiqueta')} aria-label={t('pagina_docs.buscar_documentos')} />
        <Select suelto placeholder={false} value={filterCat} onChange={e => setFilterCat(e.target.value)}
          aria-label={t('documents.filtrar_por_categoria')}
          className="ds-input docs-input-5">
          <option value="">{t('documents.todas_las_categorias')}</option>
          {CATS.map(c => <option key={c} value={c}>{etiquetaCategoria(t, c)}</option>)}
        </Select>
        <Select suelto placeholder={false} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
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
        </Select>
        <Select suelto placeholder={false} value={sortBy} onChange={e => setSortBy(e.target.value)}
          aria-label={t('pagina_docs.ordenar')}
          className="ds-input docs-input-5">
          {SORT_OPTS.map(o => <option key={o.v} value={o.v}>{t(o.l)}</option>)}
        </Select>
        <div className="ds-toolbar__spacer" />
        <div className="ds-segmented" role="group" aria-label={t('pagina_docs.vista')}>
          <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: opción de un segmentado (ds-segmented) */ aria-label={t('pagina_docs.tarjetas')} type="button" aria-pressed={viewMode === 'grid'} onClick={() => setViewMode('grid')} title={t('pagina_docs.tarjetas')}>
            <Grid3X3 size={12} />
          </Pulsable>
          <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: opción de un segmentado (ds-segmented) */ aria-label={t('pagina_docs.lista')} type="button" aria-pressed={viewMode === 'list'} onClick={() => setViewMode('list')} title={t('pagina_docs.lista')}>
            <List size={12} />
          </Pulsable>
        </div>
      </div>

      {/* Tag chips */}
      {allTags.length > 0 && (
        <div className="ds-row-wrap">
          {allTags.map(t => (
            <Pulsable type="button" key={t} aria-pressed={activeTags.includes(t)} onClick={() => toggleTag(t)}
              className={`ds-pill${activeTags.includes(t) ? ' ds-pill--accent' : ''} docs-btn-28`}
             >
              #{t}
            </Pulsable>
          ))}
          {activeTags.length > 0 && (
            <Pulsable type="button" onClick={() => setActiveTags([])}
              className="ds-pill ds-pill--danger docs-btn-28"
             >
              {t('pagina_docs.limpiar')}
            </Pulsable>
          )}
        </div>
      )}

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div className="docs-row-38">
          <span className="docs-label-14">
            {selectedIds.size}{' '}{t('pagina_docs.seleccionado_s')}
          </span>
          <Button size="sm" variant="danger" icon={<Trash2 size={14} />}
            disabled={bulkDeleteMutation.isPending}
            onClick={() => { openConfirmGlobal({ message: t('pagina_docs.eliminar_documento_s', { size: selectedIds.size }), onConfirm: () => bulkDeleteMutation.mutate(), danger: true }) }}>
            {t('pagina_docs.eliminar_seleccionados')}
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
        <EmptyState
          icon={search || filterCat || filterStatus || activeTags.length ? <Search size={28} /> : <FolderOpen size={28} />}
          title={t('documents.no_documents')}
          description={search || filterCat || filterStatus || activeTags.length ? t('pagina_docs.no_hay_resultados_para_los_filtros') : t('pagina_docs.sube_tu_primer_documento_con_el')}
          action={!search && !filterCat && !filterStatus && !activeTags.length ? (
            <Button icon={<Plus size={14} />} onClick={() => setShowUpload(true)}>{t('documents.upload')}</Button>
          ) : undefined}
        />
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
          <TablaSimple claseTabla="u-table">
            <thead>
              <tr className="docs-row-39">
                <th className="docs-td">
                  <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: casilla de seleccionar todo */ type="button" onClick={selectAll}
                    className={`docs-btn-29 document-sx16 ${selectedIds.size === docs.length && docs.length > 0 ? 'document-sx12' : 'document-sx17'} documents-page-e4`} style={{ '--documents-page-border': `2px solid ${selectedIds.size === docs.length && docs.length > 0 ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
                    {selectedIds.size === docs.length && docs.length > 0 && <Check size={9} color="white" strokeWidth={3} />}
                  </Pulsable>
                </th>
                <th aria-hidden="true" className="docs-th" />
                {[t('pagina_docs.documento'), t('pagina_docs.categoria'), t('pagina_docs.aprobacion'), t('pagina_docs.tamano'), t('pagina_docs.fecha'), t('pagina_docs.autor'), ''].map((h, i) => (
                  <th key={i} className="docs-th-2">{h}</th>
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
          </TablaSimple>
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
