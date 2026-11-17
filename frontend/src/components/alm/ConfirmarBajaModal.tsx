/**
 * Confirmación de la desactivación de una persona (licencias y hardware, fase 4).
 *
 * Antes de desactivar enseña qué licencias se liberan (ya o tras N días) y qué
 * equipos tiene que devolver, y aplica la política de la empresa
 * (`ALM_OFFBOARDING_PENDING_ASSETS`): avisar, pedir confirmación o bloquear.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserX } from 'lucide-react'
import { almIntegracionApi } from '../../services/api/almIntegracion'
import { usersApi } from '../../services/api'
import { Button, Modal, Spinner, Checkbox } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { fmtDate } from '../../utils/helpers'
import { mensajeDeError } from './almComun'
import './almIntegracion.css'

export default function ConfirmarBajaModal({ userId, nombre, onClose }: { userId: string; nombre: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [confirmo, setConfirmo] = useState(false)
  const q = useQuery({ queryKey: ['alm-previa-baja', userId], queryFn: () => almIntegracionApi.previaDeBaja(userId) })
  const m = useMutation({
    mutationFn: () => usersApi.deactivate(userId, confirmo),
    onSuccess: () => {
      toast.success(t('almint.persona_desactivada', { nombre }))
      qc.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const d = q.data
  const conEquipos = !!d && d.equipos.length > 0
  const bloqueada = conEquipos && d?.politica === 'bloquear'
  const hayQueConfirmar = conEquipos && d?.politica === 'confirmar'
  return (
    <Modal open onClose={onClose} title={t('almint.desactivar_a', { nombre })} subtitle={t('almint.desactivar_sub')}>
      {q.isLoading ? <Spinner /> : q.isError ? <p className="almint-aviso almint-aviso--peligro">{mensajeDeError(t, q.error)}</p> : d && (
        <div className="almint-form">
          <section>
            <h3 className="almint-subtitulo">{t('almint.licencias_que_se_liberan')}</h3>
            {d.licencias.length === 0 ? <p className="almint-tenue">{t('almint.sin_licencias')}</p> : <>
              <ul className="almint-checklist">{d.licencias.map(l => <li key={l.assignment_id}>{l.name}</li>)}</ul>
              <p className="almint-tenue">{d.dias_para_liberar > 0 ? t('almint.se_liberan_en', { dias: d.dias_para_liberar }) : t('almint.se_liberan_ya')}</p>
            </>}
          </section>
          <section>
            <h3 className="almint-subtitulo">{t('almint.equipos_a_devolver')}</h3>
            {d.equipos.length === 0 ? <p className="almint-tenue">{t('almint.sin_equipos')}</p> :
              <ul className="almint-checklist">{d.equipos.map(e => <li key={e.assignment_id}>
                {[e.name, e.asset_tag].filter(Boolean).join(' · ')}{e.valid_to ? ` · ${t('almint.devolver_antes_de')} ${fmtDate(e.valid_to)}` : ''}
              </li>)}</ul>}
          </section>
          {conEquipos && <p className={`almint-aviso${bloqueada ? ' almint-aviso--peligro' : ''}`}>{t(`almint.politica_${d.politica}`)}</p>}
          {hayQueConfirmar && <label className="almint-elemento">
            <span><Checkbox checked={confirmo} onChange={(_, e) => setConfirmo(e.target.checked)} /> {t('almint.confirmo_equipos_pendientes')}</span>
          </label>}
          <div className="almint-acciones almint-acciones--fin">
            <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
            <Button variant="danger" icon={<UserX size={14} />} disabled={bloqueada || (hayQueConfirmar && !confirmo)}
              loading={m.isPending} onClick={() => m.mutate()}>{t('almint.desactivar')}</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
