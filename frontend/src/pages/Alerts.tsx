import { useEffect, useState } from 'react'
import { alertErrorMessage, getAlerts } from '../services/alerts'
import type { IncidentSeverity } from '../types/incidents'
import type { AlertStatus, TrafficAlert } from '../types/alerts'

function Alerts() {
  const [status, setStatus] = useState<AlertStatus | 'all'>('active')
  const [severity, setSeverity] = useState<IncidentSeverity | ''>('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [alerts, setAlerts] = useState<TrafficAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    if (startDate && endDate && startDate > endDate) {
      setAlerts([])
      setLoading(false)
      setError(null)
      return () => {
        active = false
      }
    }
    setLoading(true)
    setError(null)
    getAlerts({
      status_filter: status,
      ...(severity ? { severity } : {}),
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {}),
    })
      .then((result) => {
        if (active) {
          setAlerts(result)
          setUpdatedAt(new Date().toLocaleString())
        }
      })
      .catch((requestError: unknown) => {
        if (active) setError(alertErrorMessage(requestError))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [status, severity, startDate, endDate])

  const invalidDateRange = !!(startDate && endDate && startDate > endDate)

  return (
    <section className="alerts-page">
      <h1>Verified hazard alerts</h1>
      <p>
        This page lists alerts derived from verified, unresolved incident reports and their
        persisted resolution status. It is not a real-time notification service.
      </p>
      <p className="report-scope-note">
        Newly submitted reports remain unverified and are listed in Reports while awaiting review.
        They appear here only after an administrator verifies them.
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, margin: '16px 0' }}>
        <label>
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value as AlertStatus | 'all')}>
            <option value="active">Active</option>
            <option value="resolved">Resolved</option>
            <option value="all">All</option>
          </select>
        </label>
        <label>
          Severity
          <select
            value={severity}
            onChange={(event) => setSeverity(event.target.value as IncidentSeverity | '')}
          >
            <option value="">All severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </label>
        <label>
          From
          <input type="date" value={startDate} max={endDate || undefined} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          Through
          <input type="date" value={endDate} min={startDate || undefined} onChange={(event) => setEndDate(event.target.value)} />
        </label>
      </div>

      {invalidDateRange && <p role="alert">Start date must be on or before end date.</p>}
      {loading && <p role="status">Loading verified incident alerts...</p>}
      {!loading && error && <p role="alert">Alerts could not be loaded: {error}</p>}
      {!loading && !error && alerts.length === 0 && (
        <p>No verified incident alerts match these filters.</p>
      )}
      {!loading && !error && alerts.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {alerts.map((alert) => (
            <li className="alert-list-item" key={alert.id}>
              <strong>{alert.type.replace(/_/g, ' ')} · {alert.severity.toUpperCase()}</strong>
              <div>Status: {alert.status} · Source: {alert.source.replace(/_/g, ' ')}</div>
              <div>
                Location: {alert.latitude.toFixed(5)}, {alert.longitude.toFixed(5)}
                {alert.road_id ? ` · Road ${alert.road_id}` : ''}
                {alert.road_reference ? ` · ${alert.road_reference}` : ''}
              </div>
              {alert.description && <p>{alert.description}</p>}
              <div>Reported: {new Date(alert.created_at).toLocaleString()}</div>
              {alert.verified_at && <div>Verified: {new Date(alert.verified_at).toLocaleString()}</div>}
              {alert.ended_at && <div>Resolved: {new Date(alert.ended_at).toLocaleString()}</div>}
            </li>
          ))}
        </ul>
      )}
      {updatedAt && <small>Data retrieved: {updatedAt}</small>}
      <p>
        Alert state follows the incident record. Acknowledgement is not stored separately; authorized
        moderators resolve the incident from Incident moderation.
      </p>
    </section>
  )
}

export default Alerts
