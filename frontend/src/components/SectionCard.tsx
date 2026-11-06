import type { ReactNode } from 'react'

interface SectionCardProps {
  title: string
  loading: boolean
  error: string | null
  isEmpty?: boolean
  emptyMessage?: string
  children: ReactNode
}

function SectionCard({ title, loading, error, isEmpty, emptyMessage, children }: SectionCardProps) {
  return (
    <section className="dashboard-section-card">
      <h2>{title}</h2>
      {loading && <p className="dashboard-card-state">Loading…</p>}
      {!loading && error && <p className="dashboard-card-error" role="alert">Error: {error}</p>}
      {!loading && !error && isEmpty && (
        <p className="dashboard-card-state">{emptyMessage ?? 'No traffic data available.'}</p>
      )}
      {!loading && !error && !isEmpty && children}
    </section>
  )
}

export default SectionCard
