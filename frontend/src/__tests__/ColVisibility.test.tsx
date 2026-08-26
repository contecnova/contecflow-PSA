import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useColVisibility } from '../components/ui/ColVisibility';

function TestColVisibility({ cols, storageKey }) {
  const { visibleCols } = useColVisibility(cols, storageKey);
  return <div>{visibleCols.map(c => <span key={c.id}>{c.label}</span>)}</div>;
}

describe('useColVisibility', () => {
  it('muestra todas las columnas por defecto', () => {
    const cols = [
      { id: 'name', label: 'Nombre', width: '2fr' },
      { id: 'age', label: 'Edad', width: '1fr' }
    ];
    render(<TestColVisibility cols={cols} storageKey="test" />);
    expect(screen.getByText('Nombre')).toBeInTheDocument();
    expect(screen.getByText('Edad')).toBeInTheDocument();
  });
});
