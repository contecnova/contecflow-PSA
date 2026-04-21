import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ResourceHeatmap from '../components/ResourceHeatmap';

describe('ResourceHeatmap', () => {
  it('renderiza el heatmap de recursos', () => {
    render(<ResourceHeatmap />);
    // Debe mostrar algún texto relacionado con carga, recursos o heatmap
    expect(screen.getByText(/carga|recurso|heatmap/i)).toBeInTheDocument();
  });
});
