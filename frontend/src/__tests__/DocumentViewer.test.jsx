import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DocumentViewer from '../components/DocumentViewer';

describe('DocumentViewer', () => {
  it('renderiza el visor de documentos', () => {
    render(<DocumentViewer />);
    // Debe mostrar algún texto relacionado con documento o versión
    expect(screen.getByText(/document|versi/i)).toBeInTheDocument();
  });
});
