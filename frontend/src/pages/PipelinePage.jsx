import { useState, useRef, useCallback } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, ClientSelect, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Megaphone } from 'lucide-react'
import { fmtCurrency, fmtDate, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'

export default function PipelinePage() {
  return (
    <div style={{ padding: 20 }}>
      <PageHeader icon={<Megaphone size={16} />} title="Pipeline" />
      <p>Pipeline functionality</p>
    </div>
  )
}

function OppFormModal({ opp, onClose }) {
  return (
    <Modal onClose={onClose}>
      <h2>Oportunidad Modal</h2>
    </Modal>
  )
}
