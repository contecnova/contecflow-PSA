import type { CSSProperties, ReactNode } from 'react'
import { FixedSizeList } from 'react-window'

/**
 * VirtualList — renders only visible rows for large datasets.
 */
export interface VirtualListProps<T> {
  items?: T[]
  renderRow: (item: T, index: number) => ReactNode
  rowHeight?: number
  height?: number
  className?: string
}

interface RowProps {
  index: number
  style: CSSProperties
}

export default function VirtualList<T>({
  items = [],
  renderRow,
  rowHeight = 56,
  height = 600,
  className = '',
}: VirtualListProps<T>) {
  const Row = ({ index, style }: RowProps) => (
    <div style={style}>
      {renderRow(items[index], index)}
    </div>
  )

  return (
    <div className={className}>
      <FixedSizeList
        height={height}
        itemCount={items.length}
        itemSize={rowHeight}
        width="100%"
      >
        {Row}
      </FixedSizeList>
    </div>
  )
}
