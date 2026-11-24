/**
 * Chip vivo dentro de una nota: `#` tarea, ticket, proyecto, cliente (o lo creado
 * desde la nota: demanda, idea de cartera, recordatorio) y `@` persona. Muestra
 * el estado actual; si quien lee no puede verlo, sale «sin acceso» sin título.
 */
import { useEffect, useState } from 'react'
import type { NodeViewProps } from '@tiptap/react'
import { NodeViewWrapper } from '@tiptap/react'
import { useNavigate } from 'react-router-dom'
import { AtSign, Calendar, CheckSquare, FolderOpen, Hash, Lightbulb, Lock, Ticket, UserCheck, ClipboardList } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Pulsable } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import type { Chip } from '../../services/api/cuaderno'
import { resolverChip } from './resolverChips'

const ICONOS: Record<string, LucideIcon> = {
  task: CheckSquare, ticket: Ticket, project: FolderOpen, client: UserCheck, user: AtSign,
  demand: ClipboardList, proposal: Lightbulb, event: Calendar,
}

export default function ChipVivo({ node, extension }: NodeViewProps) {
  const t = useAppT()
  const navigate = useNavigate()
  const tipo = extension.name === 'mention' ? 'user' : String(node.attrs.type || '')
  const id = String(node.attrs.id || '')
  const [chip, setChip] = useState<Chip | null>(null)

  useEffect(() => {
    let vivo = true
    if (tipo && id) void resolverChip(tipo, id).then(c => { if (vivo) setChip(c) })
    return () => { vivo = false }
  }, [tipo, id])

  const Icono = chip?.hidden ? Lock : (ICONOS[tipo] || Hash)
  const oculto = !!chip?.hidden
  const etiqueta = oculto ? t('cuaderno.chip_sin_acceso') : (chip?.label || String(node.attrs.label || '') || '…')
  const estado = !oculto && chip?.status && tipo !== 'user' && tipo !== 'event'
    ? etiquetaCodigo(t, 'cuaderno_estado', String(chip.status)) : null
  const ir = () => { if (!oculto && chip?.url) navigate(chip.url) }
  const cuerpo = (
    <>
      <Icono size={12} aria-hidden />
      <span className="cdn-chip__texto">{tipo === 'user' && !oculto ? `@${etiqueta}` : etiqueta}</span>
      {estado && <span className="cdn-chip__estado">{estado}</span>}
    </>
  )

  return (
    <NodeViewWrapper as="span" className={`cdn-chip cdn-chip--${tipo}${oculto ? ' cdn-chip--oculto' : ''}`}
      data-tipo={tipo} contentEditable={false}>
      {chip?.url && !oculto ? (
        <Pulsable className="cdn-chip__cuerpo" title={etiqueta} onClick={ir}>{cuerpo}</Pulsable>
      ) : (
        <span className="cdn-chip__cuerpo" title={oculto ? t('cuaderno.chip_sin_acceso_ayuda') : etiqueta}>{cuerpo}</span>
      )}
    </NodeViewWrapper>
  )
}
