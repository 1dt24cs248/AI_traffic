import type { CSSProperties, ReactNode } from 'react'

interface SectionCardProps {
  title: string
  loading: boolean
  error: string | null
  isEmpty?: boolean
  emptyMessage?: string
  children: ReactNode
}

const cardStyle: CSSProperties = {
  border: '1px solid #e0e0e0',
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
  backgroundColor: '#ffffff',
  boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
}

const titleStyle: CSSProperties = {
  marginTop: 0,
  marginBottom: 16,
  fontSize: 18,
  fontWeight: 600,
  color: '#1a1a2e',
}

function SectionCard({ title, loading, error, isEmpty, emptyMessage, children }: SectionCardProps) {
  return (
    <section style={cardStyle}>
      <h2 style={titleStyle}>{title}</h2>
      {loading && <p style={{ color: '#666' }}>Loading...</p>}
      {!loading && error && <p style={{ color: '#b00020' }}>Error: {error}</p>}
      {!loading && !error && isEmpty && (
        <p style={{ color: '#666' }}>{emptyMessage ?? 'No traffic data available.'}</p>
      )}
      {!loading && !error && !isEmpty && children}
    </section>
  )
}

export default SectionCard