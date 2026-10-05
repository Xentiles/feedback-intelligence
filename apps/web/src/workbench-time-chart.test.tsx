import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { InspectionProvider } from './inspection-components'
import { WorkbenchTimeChart } from './workbench-time-chart'
import { type DailySeriesRow } from './time-aggregation'

afterEach(cleanup)
describe('inspectable Workbench volume chart', () => {
  const dailySeries: DailySeriesRow[] = [
    { date: '2026-09-01', total: 4, topics: { service: 3, unclassified: 1 } },
    { date: '2026-09-03', total: 2, topics: { service: 2 } },
  ]

  it('supports one chart focus target, arrow selection, pinned details and explicit inclusive-date drilldown', () => {
    const drilldown = vi.fn()
    render(
      <InspectionProvider scope="run-a">
        <WorkbenchTimeChart
          dailySeries={dailySeries}
          onDrillDown={drilldown}
          provenance={[{ label: 'Run ID', value: 'run-a' }]}
        />
      </InspectionProvider>,
    )
    const chart = screen.getByRole('button', {
      name: /Inspect observed record volume/,
    })
    expect(chart).toHaveAttribute('tabindex', '0')
    fireEvent.focus(chart)
    fireEvent.keyDown(chart, { key: 'Home' })
    expect(chart).toHaveAccessibleName(/2026-09-01/)
    fireEvent.keyDown(chart, { key: 'Enter' })
    const panel = screen.getByRole('complementary', { name: '2026-09-01' })
    expect(within(panel).getByText('run-a')).toBeInTheDocument()
    expect(within(panel).getByText('3/4 · 75.0%')).toBeInTheDocument()
    expect(drilldown).not.toHaveBeenCalled()
    fireEvent.click(
      within(panel).getByRole('button', { name: 'View matching records' }),
    )
    expect(drilldown).toHaveBeenCalledWith('2026-09-01', '2026-09-01')
    expect(chart).toHaveFocus()
  })

  it('marks missing coverage and makes its alternative table inspectable without inventing zero', () => {
    render(
      <InspectionProvider scope="run-a">
        <WorkbenchTimeChart dailySeries={dailySeries} onDrillDown={vi.fn()} />
      </InspectionProvider>,
    )
    const chart = screen.getByRole('button', {
      name: /Inspect observed record volume/,
    })
    fireEvent.keyDown(chart, { key: 'Home' })
    fireEvent.keyDown(chart, { key: 'ArrowRight' })
    fireEvent.keyDown(chart, { key: ' ' })
    const panel = screen.getByRole('complementary', { name: '2026-09-02' })
    expect(within(panel).getByText('Unknown')).toBeInTheDocument()
    expect(
      within(panel).queryByRole('button', { name: 'View matching records' }),
    ).not.toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByText('Chart periods and coverage'))
    const table = screen.getByRole('region', { name: 'Observed period counts' })
    expect(within(table).getByText('Unknown coverage')).toBeInTheDocument()
    fireEvent.click(within(table).getByRole('button', { name: '2026-09-03' }))
    expect(
      screen.getByRole('complementary', { name: '2026-09-03' }),
    ).toBeInTheDocument()
  })

  it('draws only bounded buckets for the larger scenario and handles absent dates', () => {
    const source = Array.from({ length: 450 }, (_, index) => ({
      date: new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10),
      total: 4,
      topics: { service: 4 },
    }))
    const { container, rerender } = render(
      <InspectionProvider scope="run-a">
        <WorkbenchTimeChart dailySeries={source} onDrillDown={vi.fn()} />
      </InspectionProvider>,
    )
    expect(
      container.querySelectorAll('.wb-volume-chart__bar').length,
    ).toBeLessThanOrEqual(60)
    expect(container.querySelector('svg')).toHaveAttribute(
      'viewBox',
      '0 0 720 280',
    )
    rerender(
      <InspectionProvider scope="run-a">
        <WorkbenchTimeChart dailySeries={[]} onDrillDown={vi.fn()} />
      </InspectionProvider>,
    )
    expect(
      screen.getByText('No dated records; time analysis is unavailable.'),
    ).toBeInTheDocument()
  })

  it('preserves inspection without offering unavailable date drilldown on older runtimes', () => {
    render(
      <InspectionProvider scope="earlier-run">
        <WorkbenchTimeChart dailySeries={dailySeries} />
      </InspectionProvider>,
    )
    const chart = screen.getByRole('button', {
      name: /Inspect observed record volume/,
    })
    fireEvent.keyDown(chart, { key: 'Enter' })
    const panel = screen.getByRole('complementary', { name: '2026-09-03' })
    expect(within(panel).getByText('Classified records')).toBeInTheDocument()
    expect(
      within(panel).queryByRole('button', { name: 'View matching records' }),
    ).not.toBeInTheDocument()
  })
})
