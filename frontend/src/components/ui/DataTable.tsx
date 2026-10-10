import type { ReactNode } from 'react'
import { EmptyState } from './EmptyState'

export interface DataColumn<T> {
  header: ReactNode
  render: (row: T) => ReactNode
  className?: string
  align?: 'right'
}

export function DataTable<T>({
  columns, rows, rowKey, empty, noWrap = true,
}: {
  columns: DataColumn<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => string
  empty?: ReactNode
  noWrap?: boolean
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line">
        {empty ?? <EmptyState title="Nothing here yet" hint="There are no records to show." />}
      </div>
    )
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          {columns.map((c, i) => (
            <th key={i} className={c.align === 'right' ? 'text-right' : ''}>{c.header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={rowKey(row, i)} className="bg-surface">
            {columns.map((c, i) => (
              <td key={i} data-label={String(c.header ?? '')} className={noWrap ? 'td-value' : ''}>
                <span className={c.align === 'right' ? 'td-value ml-auto text-right' : ''}>{c.render(row)}</span>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}