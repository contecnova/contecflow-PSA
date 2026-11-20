/**
 * Participantes y consentimiento (19-11-2026).
 *
 * - Cada persona de la empresa da o niega su propio consentimiento (`self`).
 * - El gestor anota el de un asistente externo: verbal o por escrito, o su
 *   negativa. Un «no» tacha lo que dijo antes del análisis (servidor).
 * - El gestor añade (nombre, correo o persona de la empresa) y quita asistentes.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, ShieldCheck, Trash2, Users } from 'lucide-react'
import { Button, Card, Confirm, IconButton, Input, Section, StatusBadge, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { MetodoConsentimiento, ParticipanteReunion, ReunionDetalle } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

function EstadoDeConsentimiento({ p }: { p: ParticipanteReunion }) {
  const t = useAppT()
  if (p.consent === true) {
    return (
      <StatusBadge kind="success" caps={false} title={p.consent_at ? fmtDateTime(p.consent_at) : undefined}>
        {t('reuniones.consentimiento.si')}{p.consent_method ? ` · ${t(`reuniones.consentimiento.metodo_${p.consent_method}`, p.consent_method)}` : ''}
      </StatusBadge>
    )
  }
  if (p.consent === false) return <StatusBadge kind="danger" caps={false}>{t('reuniones.consentimiento.no')}</StatusBadge>
  return <StatusBadge kind="warning" caps={false}>{t('reuniones.consentimiento.sin_respuesta')}</StatusBadge>
}

export default function ParticipantesDeReunion({ reunion }: { reunion: ReunionDetalle }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const yo = useAuth().user?.id
  const gestor = reunion.permissions.manage
  const [alta, setAlta] = useState(false)
  const [nombre, setNombre] = useState('')
  const [correo, setCorreo] = useState('')
  const [persona, setPersona] = useState('')
  const [quitar, setQuitar] = useState<ParticipanteReunion | null>(null)

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: CLAVES.detalle(reunion.id) })
    qc.invalidateQueries({ queryKey: CLAVES.lista })
  }
  const alFallar = (e: unknown) => toast.error(extractErr(e))

  const consentir = useMutation({
    mutationFn: (c: { participant_id?: string; consents: boolean; method?: MetodoConsentimiento }) => reunionesApi.consentir(reunion.id, c),
    onSuccess: () => { toast.success(t('reuniones.consentimiento.anotado')); refrescar() },
    onError: alFallar,
  })
  const anadir = useMutation({
    mutationFn: () => reunionesApi.anadirParticipante(reunion.id, { name: nombre.trim(), email: correo.trim() || null, user_id: persona || null }),
    onSuccess: () => { setAlta(false); setNombre(''); setCorreo(''); setPersona(''); refrescar() },
    onError: alFallar,
  })
  const borrar = useMutation({
    mutationFn: (pid: string) => reunionesApi.quitarParticipante(reunion.id, pid),
    onSuccess: () => { setQuitar(null); refrescar() },
    onError: alFallar,
  })

  return (
    <Card>
      <Section
        title={<span className="reu-seccion"><Users size={16} aria-hidden />{t('reuniones.participantes.titulo', { n: reunion.participants.length })}</span>}
        subtitle={reunion.consent.required ? t('reuniones.consentimiento.exigido') : undefined}
        actions={gestor ? <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setAlta(a => !a)}>{t('reuniones.anadir_participante')}</Button> : undefined}
      >
        {reunion.consent.notice_confirmed_at && (
          <p className="u-text3-xs reu-meta">
            <ShieldCheck size={13} aria-hidden />
            {t('reuniones.consentimiento.aviso_confirmado', { quien: reunion.consent.notice_confirmed_by ?? '—', fecha: fmtDateTime(reunion.consent.notice_confirmed_at) })}
          </p>
        )}

        {alta && (
          <div className="reu-alta">
            <Input aria-label={t('reuniones.campo.nombre')} placeholder={t('reuniones.campo.nombre')} value={nombre} onChange={e => setNombre(e.target.value)} />
            <Input aria-label={t('reuniones.campo.correo')} placeholder={t('reuniones.campo.correo')} type="email" value={correo} onChange={e => setCorreo(e.target.value)} />
            <UserSelect value={persona} placeholder={t('reuniones.participantes.persona_opcional')}
              onChange={(id, u) => { setPersona(id); if (u?.full_name && !nombre.trim()) setNombre(u.full_name) }} />
            <Button size="sm" loading={anadir.isPending} disabled={!nombre.trim()} onClick={() => anadir.mutate()}>{t('reuniones.anadir')}</Button>
          </div>
        )}

        {reunion.participants.length === 0 ? <p className="u-text3-xs">{t('reuniones.participantes.vacio')}</p> : (
          <ul className="reu-lista">
            {reunion.participants.map(p => {
              const soyYo = !!yo && p.user_id === yo
              const externo = !p.user_id
              return (
                <li key={p.id} className="reu-participante">
                  <div className="u-flex1-min0">
                    <div className="reu-participante__nombre">{p.name}</div>
                    <div className="reu-accion__meta">
                      {p.email && <span className="u-text3-xs">{p.email}</span>}
                      <span className="u-text3-xs">{t(`reuniones.participantes.rol_${p.role}`)}</span>
                      {externo && <span className="u-text3-xs">{t('reuniones.participantes.externo')}</span>}
                    </div>
                  </div>
                  <div className="reu-accion__botones">
                    <EstadoDeConsentimiento p={p} />
                    {soyYo && (
                      <>
                        <Button size="xs" variant="secondary" disabled={p.consent === true || consentir.isPending}
                          onClick={() => consentir.mutate({ consents: true, method: 'self' })}>{t('reuniones.consentimiento.doy')}</Button>
                        <Button size="xs" variant="ghost" disabled={p.consent === false || consentir.isPending}
                          onClick={() => consentir.mutate({ consents: false, method: 'self' })}>{t('reuniones.consentimiento.niego')}</Button>
                      </>
                    )}
                    {gestor && externo && (
                      <>
                        <Button size="xs" variant="secondary" disabled={consentir.isPending}
                          onClick={() => consentir.mutate({ participant_id: p.id, consents: true, method: 'verbal' })}>{t('reuniones.consentimiento.verbal')}</Button>
                        <Button size="xs" variant="secondary" disabled={consentir.isPending}
                          onClick={() => consentir.mutate({ participant_id: p.id, consents: true, method: 'written' })}>{t('reuniones.consentimiento.escrito')}</Button>
                        <Button size="xs" variant="ghost" disabled={consentir.isPending}
                          onClick={() => consentir.mutate({ participant_id: p.id, consents: false, method: 'verbal' })}>{t('reuniones.consentimiento.no_consiente')}</Button>
                      </>
                    )}
                    {gestor && (
                      <IconButton ariaLabel={t('reuniones.quitar')} onClick={() => setQuitar(p)}><Trash2 size={14} aria-hidden /></IconButton>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Section>
      <Confirm open={!!quitar} title={t('reuniones.participantes.quitar_titulo')}
        description={t('reuniones.participantes.quitar_desc', { nombre: quitar?.name ?? '' })}
        loading={borrar.isPending} onCancel={() => setQuitar(null)} onConfirm={() => quitar && borrar.mutate(quitar.id)} />
    </Card>
  )
}
