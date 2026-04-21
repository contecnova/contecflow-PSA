import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DocumentsPanel from '../components/DocumentsPanel';

describe('DocumentsPanel', () => {
  it('renderiza el panel de documentos', () => {
    render(<DocumentsPanel />);
    // Debe mostrar algún texto relacionado con documentos
    expect(screen.getByText(/document/i)).toBeInTheDocument();
  });
});
