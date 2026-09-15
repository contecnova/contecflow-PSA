import { describe, it, expect } from 'vitest';
import { render, screen} from '@testing-library/react';
import { useSort } from '../components/ui/TableControls';

function TestTable({ data }: { data: Array<{ name: string }> }) {
  const { setSort, sortedData } = useSort(data, 'name');
  return (
    <table>
      <thead>
        <tr>
          <th onClick={() => setSort('name')}>Nombre</th>
        </tr>
      </thead>
      <tbody>
        {sortedData.map((row, i) => (
          <tr key={i}><td>{row.name}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

describe('useSort (TableControls)', () => {
  it('ordena los datos por nombre', () => {
    const data = [
      { name: 'Zeta' },
      { name: 'Alpha' },
      { name: 'Beta' }
    ];
    render(<TestTable data={data} />);
    const rows = screen.getAllByRole('row');
    // Primer row es header, los siguientes son datos ordenados
    expect(rows[1]).toHaveTextContent('Alpha');
    expect(rows[2]).toHaveTextContent('Beta');
    expect(rows[3]).toHaveTextContent('Zeta');
  });
});
