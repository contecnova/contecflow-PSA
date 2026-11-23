/**
 * WorkflowDesignerPage — diseñador visual de workflows para Service Desk.
 *
 * Reescrito sobre ReactFlow (`@xyflow/react`):
 *   • Lista de blueprints: búsqueda + filtro por process_type + clonar/archivar.
 *   • Catálogo de plantillas (incident triage, change approval, vacaciones).
 *   • Editor con paleta extensible (start/end/state/decision/approval/wait/notify/
 *     http_call/create_ticket), panel de propiedades, mini-map, snap-to-grid,
 *     validación en vivo (errors/warnings) y autosave manual.
 *   • Versiones: guardar, publicar, indicador del último publicado.
 *
 * URL state: `/sd/workflow-designer?id=<blueprint_id>` selecciona el editor.
 *
 * 16-11-2026 (pasada de diseño): título del menú y sin "blueprints" en los
 * textos (ahora "flujos"); acciones principales en la cabecera (Nuevo flujo,
 * Desde plantilla); pestañas Editor/Ejecuciones con Tabs del kit; iconos de
 * nodo lucide (antes emojis); vacíos con EmptyState; estados con StatusBadge;
 * botones con la prop `icon`; campos con ds-input; tipo de entidad con selector
 * y ramas (approved, next…) traducidas en el lienzo y en el historial.
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { GitBranch, Plus, Sparkles } from 'lucide-react'
import { Button, Page } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import './WorkflowDesignerPage.css'
import { BlueprintList, CreateBlueprintModal, TemplatePickerModal } from './WorkflowDesignerListado'
import { BlueprintEditor } from './WorkflowDesignerEditor'

// ── Top-level page ───────────────────────────────────────────────────────────
export default function WorkflowDesignerPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeId = searchParams.get('id')
  const { t: traducir } = useAppLang()
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const abrir = (id: string) => setSearchParams({ id })

  return (
    <Page
      icon={<GitBranch size={18} />}
      title={traducir('workflowdesigner.titulo')}
      subtitle={traducir('workflowdesigner.subtitulo')}
      actions={activeId ? undefined : (
        <>
          <Button variant="secondary" icon={<Sparkles size={14} />} onClick={() => setShowTemplates(true)}>
            {traducir('workflowdesigner.plantilla')}
          </Button>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
            {traducir('workflowdesigner.nuevo_blueprint')}
          </Button>
        </>
      )}
    >
      {activeId
        ? <BlueprintEditor id={activeId} onBack={() => setSearchParams({})} />
        : <BlueprintList onOpen={abrir} onNew={() => setShowCreate(true)} />}
      {showCreate && (
        <CreateBlueprintModal
          onClose={() => setShowCreate(false)}
          onCreated={bp => { setShowCreate(false); abrir(bp.id) }}
        />
      )}
      {showTemplates && (
        <TemplatePickerModal
          onClose={() => setShowTemplates(false)}
          onPicked={bp => { setShowTemplates(false); abrir(bp.id) }}
        />
      )}
    </Page>
  )
}

