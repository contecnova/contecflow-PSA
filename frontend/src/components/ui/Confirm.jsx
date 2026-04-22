import React from 'react';
import { Modal, Button, Spinner } from './index';
import { useAppT } from '../../i18n/AppLangContext';

/**
 * Confirm — Simple confirmation dialog
 * Props:
 * - open: boolean
 * - title: string
 * - description: string
 * - onCancel: function
 * - onConfirm: function
 * - loading: boolean
 */
export default function Confirm({ open, title, description, onCancel, onConfirm, loading }) {
  const t = useAppT();
  return (
    <Modal open={open} onClose={onCancel} title={title} width={400}>
      <div style={{ marginBottom: 20 }}>{description}</div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button variant="secondary" onClick={onCancel} disabled={loading}>
          {t('common.cancel')}
        </Button>
        <Button variant="danger" onClick={onConfirm} loading={loading}>
          {loading ? <Spinner size={16} /> : t('common.confirm')}
        </Button>
      </div>
    </Modal>
  );
}
