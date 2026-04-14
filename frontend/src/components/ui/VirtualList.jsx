import { FixedSizeList } from 'react-window'

/**
 * VirtualList — renders only visible rows for large datasets.
 *
 * Props:
 *   items      — full array of data items
 *   renderRow  — (item, index) => ReactNode  (must apply the provided `style` for positioning)
 *   rowHeight  — pixel height of each row (default 56)
 *   height     — pixel height of the scrollable container (default 600)
 *   className  — optional CSS class for the outer wrapper
 */
export default function VirtualList({
  items = [],
  renderRow,
  rowHeight = 56,
  height = 600,
  className = '',
}) {
  const Row = ({ index, style }) => (
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
