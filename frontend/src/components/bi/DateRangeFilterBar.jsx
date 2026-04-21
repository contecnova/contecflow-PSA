import { useState, useCallback } from 'react'
import { Calendar } from 'lucide-react'
import { useAppT } from '../../hooks/useAppT'

const RANGE_PRESETS = {
  week: { key: 'date_range_filter.week', days: 7 },
  month: { key: 'date_range_filter.month', days: 30 },
  quarter: { key: 'date_range_filter.quarter', days: 90 },
  year: { key: 'date_range_filter.year', days: 365 },
}

export default function DateRangeFilterBar({ dateFrom, dateTo, onDateChange, disabled = false }) {
  const t = useAppT()
  const [customOpen, setCustomOpen] = useState(false)
  const [localFrom, setLocalFrom] = useState(dateFrom || '')
  const [localTo, setLocalTo] = useState(dateTo || '')

  const applyPreset = useCallback((days) => {
    const to = new Date()
    const from = new Date(to)
    from.setDate(to.getDate() - (days - 1))
    onDateChange({
      date_from: from.toISOString().slice(0, 10),
      date_to:   to.toISOString().slice(0, 10),
    })
  }, [onDateChange])

  const applyCustom = useCallback(() => {
    if (localFrom && localTo) {
      onDateChange({ date_from: localFrom, date_to: localTo })
      setCustomOpen(false)
    }
  }, [localFrom, localTo, onDateChange])

  const getLabel = () =>
    dateFrom && dateTo ? `${dateFrom} — ${dateTo}` : t('date_range_filter.select_range')

  const btnBase = {
    padding: '4px 12px',
    fontSize: '0.875em',
    borderRadius: '6px',
    border: '1px solid var(--border-color, #d1d5db)',
    background: 'var(--surface-3, transparent)',
    color: 'var(--text-1, #222)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    fontFamily: 'inherit',
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
        flexWrap: 'wrap',
        background: 'var(--surface-2)',
        padding: '10px 14px',
        border: '1px solid var(--surface-4, #e5e7eb)',
        borderRadius: '0.5rem',
        color: 'var(--text-1, #222)',
      }}
    >
      <Calendar style={{ width: 15, height: 15, color: 'var(--text-3, #666)', flexShrink: 0 }} />
      <span style={{ fontSize: '0.875em', fontWeight: 500, color: 'var(--text-2)' }}>
        {t('date_range_filter.period')}
      </span>

      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
        {Object.entries(RANGE_PRESETS).map(([key, preset]) => (
          <button
            key={key}
            onClick={() => applyPreset(preset.days)}
            disabled={disabled}
            style={btnBase}
          >
            {t(preset.key)}
          </button>
        ))}
      </div>

      <button
        onClick={() => setCustomOpen((v) => !v)}
        disabled={disabled}
        style={{ ...btnBase, marginLeft: '4px' }}
      >
        {t('date_range_filter.custom')}
      </button>

      {customOpen && (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="date"
            value={localFrom}
            onChange={(e) => setLocalFrom(e.target.value)}
            disabled={disabled}
            style={{
              border: '1px solid var(--surface-4, #d1d5db)',
              borderRadius: '6px',
              padding: '3px 8px',
              fontSize: '0.875em',
              background: 'var(--surface-1, #fff)',
              color: 'var(--text-1, #222)',
              fontFamily: 'inherit',
            }}
          />
          <span style={{ color: 'var(--text-3)' }}>—</span>
          <input
            type="date"
            value={localTo}
            onChange={(e) => setLocalTo(e.target.value)}
            disabled={disabled}
            style={{
              border: '1px solid var(--surface-4, #d1d5db)',
              borderRadius: '6px',
              padding: '3px 8px',
              fontSize: '0.875em',
              background: 'var(--surface-1, #fff)',
              color: 'var(--text-1, #222)',
              fontFamily: 'inherit',
            }}
          />
          <button
            onClick={applyCustom}
            disabled={disabled || !localFrom || !localTo}
            style={{
              ...btnBase,
              background: 'var(--primary, #2563eb)',
              color: '#fff',
              border: 'none',
              opacity: (disabled || !localFrom || !localTo) ? 0.5 : 1,
              cursor: (disabled || !localFrom || !localTo) ? 'not-allowed' : 'pointer',
            }}
          >
            {t('date_range_filter.apply')}
          </button>
        </div>
      )}

      <span style={{ marginLeft: 'auto', fontSize: '0.8em', color: 'var(--text-3, #666)' }}>
        {getLabel()}
      </span>
    </div>
  )
}
