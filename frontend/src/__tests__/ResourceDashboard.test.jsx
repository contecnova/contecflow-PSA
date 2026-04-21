import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ResourceDashboard from '../components/ResourceDashboard';

describe('ResourceDashboard', () => {
  it('renderiza el dashboard de recursos', () => {
    render(<ResourceDashboard />);
    // Debe mostrar algún texto relacionado con recursos o equipo
    expect(screen.getByText(/recurso|equipo|team/i)).toBeInTheDocument();
  });
});
