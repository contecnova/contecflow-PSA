/**
 * Mis preferencias del asistente de reuniones (19-11-2026): recoger mis
 * reuniones de Teams y de Meet al terminar, mandar el bot a las reuniones de
 * mi calendario e idioma en que quiero leerlas. Lo que la empresa no tiene
 * activado sale deshabilitado con su explicación.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Select, Spinner, Switch } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { LANGUAGES } from '../../i18n/portalTranslations'
import { reunionesApi } from '../../services/api/reuniones'
import type { PreferenciasReuniones } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

export default function ModalPreferencias({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: CLAVES.preferencias, queryFn: reunionesApi.preferencias })
  const [borrador, setBorrador] = useState<PreferenciasReuniones | null>(null)

  useEffect(() => {
    if (data && !borrador) {
      setBorrador({ collect_teams: data.collect_teams, collect_meet: data.collect_meet, bot_for_my_calendar: data.bot_for_my_calendar, language: data.language })
    }
  }, [data, borrador])

  const guardar = useMutation({
    mutationFn: (p: PreferenciasReuniones) => reunionesApi.guardarPreferencias(p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLAVES.preferencias })
      toast.success(t('reuniones.preferencias.guardadas'))
      onClose()
    },
    onError: e => toast.error(extractErr(e)),
  })

  const disp = data?.available ?? { teams: false, meet: false, bots: false }
  const cambiar = <K extends keyof PreferenciasReuniones>(k: K, v: PreferenciasReuniones[K]) =>
    setBorrador(b => (b ? { ...b, [k]: v } : b))

  return (
    <Modal open title={t('reuniones.preferencias.titulo')} subtitle={t('reuniones.preferencias.subtitulo')} onClose={onClose}>
      {isLoading || !borrador ? <Spinner /> : (
        <div className="reu-form reu-form--una">
          <Switch checked={borrador.collect_teams} disabled={!disp.teams} onChange={v => cambiar('collect_teams', v)}
            label={t('reuniones.preferencias.recoger_teams')}
            ayuda={disp.teams ? t('reuniones.preferencias.recoger_teams_ayuda') : t('reuniones.preferencias.no_disponible')} />
          <Switch checked={borrador.collect_meet} disabled={!disp.meet} onChange={v => cambiar('collect_meet', v)}
            label={t('reuniones.preferencias.recoger_meet')}
            ayuda={disp.meet ? t('reuniones.preferencias.recoger_meet_ayuda') : t('reuniones.preferencias.no_disponible')} />
          <Switch checked={borrador.bot_for_my_calendar} disabled={!disp.bots} onChange={v => cambiar('bot_for_my_calendar', v)}
            label={t('reuniones.preferencias.bot_calendario')}
            ayuda={disp.bots ? t('reuniones.preferencias.bot_calendario_ayuda') : t('reuniones.preferencias.no_disponible')} />
          <Select label={t('reuniones.preferencias.idioma')} hint={t('reuniones.preferencias.idioma_ayuda')}
            value={borrador.language ?? ''} onChange={e => cambiar('language', e.target.value || null)}
            placeholder={t('reuniones.preferencias.idioma_interfaz')}
            options={LANGUAGES.map(l => ({ value: l.code, label: l.label }))} />
          <div className="reu-botonera">
            <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
            <Button loading={guardar.isPending} onClick={() => guardar.mutate(borrador)}>{t('common.save')}</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
