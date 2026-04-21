import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import GanttChart from '../components/GanttChart';

describe('GanttChart', () => {
  it('renderiza el componente GanttChart', () => {
    render(<GanttChart />);
    // Debe mostrar algún texto o elemento SVG relacionado con Gantt
    expect(screen.getByText(/gantt|tarea|proyecto/i)).toBeInTheDocument();
  });
});
