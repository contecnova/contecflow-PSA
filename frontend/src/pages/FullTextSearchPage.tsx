import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'
export default function FullTextSearchPage(): JSX.Element | null {
  const _t = useAppT()
  const navigate = useNavigate()
  useEffect(() => { navigate('/search', { replace: true }) }, [navigate])
  return null
}
