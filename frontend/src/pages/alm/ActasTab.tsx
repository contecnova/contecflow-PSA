/** Actas de entrega y devolución (fase 1): las pendientes de firma y el resto, con PDF y fotos. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileSignature } from 'lucide-react'
import { EmptyState, Spinner, Select } from '../../components/ui'
import { useAppT } from '../../i18n/AppLangContext'
import { almApi } from '../../services/api/alm'
import { TarjetaDeActa } from '../../components/alm/FichaActivo'

export default function ActasTab() {
  const t = useAppT()
  const [estado, setEstado] = useState('pending_signature')
  const { data = [], isLoading } = useQuery({
    queryKey: ['alm-acts', 'todas', estado],
    queryFn: () => almApi.actas(estado ? { status: estado } : {}),
  })
  return (
    <div>
      <div className="almf-filtros">
        <div className="almf-filtro">
          <Select label={t('alm.status')} placeholder={false} id="alma-est" value={estado} onChange={e => setEstado(e.target.value)}>
            <option value="pending_signature">{t('alm.st_pending_signature')}</option>
            <option value="signed">{t('alm.st_signed')}</option>
            <option value="unsigned">{t('alm.st_unsigned')}</option>
            <option value="void">{t('alm.st_void')}</option>
            <option value="">{t('alm.filter_all')}</option>
          </Select>
        </div>
      </div>
      <p className="alm-hint">{t('alm.acts_hint')}</p>
      {isLoading ? <Spinner /> : data.length === 0
        ? <EmptyState svgIcon={<FileSignature size={32} />} title={t('alm.acts_empty')} />
        : <ul className="almf-lista">{data.map(a => <TarjetaDeActa key={a.id} acta={a} />)}</ul>}
    </div>
  )
}
