import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'
export default function WikiTagsPage() {
  const _t = useAppT()
  const navigate = useNavigate()
  useEffect(() => { navigate('/wiki', { replace: true }) }, [navigate])
  return null
}
