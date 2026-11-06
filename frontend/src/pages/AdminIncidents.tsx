import { useCallback, useEffect, useState } from 'react'
import { getCurrentUser } from '../services/auth'
import {
  extractIncidentError,
  getIncidents,
  rejectIncident,
  resolveIncident,
  verifyIncident,
} from '../services/incidents'
import type { CurrentUser } from '../types/auth'
import type { Incident } from '../types/incidents'

function AdminIncidents() {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [moderatingId, setModeratingId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<Incident['status'] | 'all'>('reported')

  const loadReports = useCallback(async (showLoading: boolean) => {
    if (showLoading) setLoading(true)
    else setRefreshing(true)
    setError(null)
    try {
      const currentUser = await getCurrentUser()
      setUser(currentUser)
      if (currentUser.role !== 'ADMIN') {
        setIncidents([])
        return
      }
      setIncidents(await getIncidents(
        statusFilter === 'all' ? undefined : statusFilter,
        statusFilter === 'all',
      ))
    } catch (err) {
      setError(extractIncidentError(err))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [statusFilter])

  useEffect(() => {
    void loadReports(true)
  }, [loadReports])

  async function handleModeration(incidentId: string, action: 'verify' | 'reject' | 'resolve') {
    setModeratingId(incidentId)
    setError(null)
    setNotice(null)
    try {
      const updated = action === 'verify'
        ? await verifyIncident(incidentId)
        : action === 'reject'
          ? await rejectIncident(incidentId)
          : await resolveIncident(incidentId)
      setNotice(
        action === 'verify'
          ? `Incident ${updated.id} verified. Refresh affected routes to update feasibility.`
          : action === 'reject'
            ? `Incident ${updated.id} rejected. It will not appear in active alerts.`
            : `Incident ${updated.id} resolved.`,
      )
      await loadReports(false)
    } catch (err) {
      setError(extractIncidentError(err))
    } finally {
      setModeratingId(null)
    }
  }

  return (
    <section className="admin-incidents-page">
      <h1>Incident moderation</h1>
      <p>Review submitted reports. Verification is required before a full road closure can constrain routing.</p>

      <label>
        Report status
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as Incident['status'] | 'all')}
          style={{ display: 'block', padding: 8, margin: '8px 0 16px' }}
        >
          <option value="reported">Reported</option>
          <option value="verified">Verified</option>
          <option value="rejected">Rejected</option>
          <option value="resolved">Resolved</option>
          <option value="all">All reports</option>
        </select>
      </label>

      {loading && <p role="status">Checking administrator access and loading reports...</p>}
      {!loading && error && <p role="alert">Incident moderation unavailable: {error}</p>}
      {!loading && !error && user?.role !== 'ADMIN' && (
        <p role="alert">Administrator access is required to verify incident reports.</p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!loading && !error && user?.role === 'ADMIN' && (
        <>
          <button
            type="button"
            onClick={() => void loadReports(false)}
            disabled={refreshing || moderatingId !== null}
          >
            {refreshing ? 'Refreshing reports...' : 'Refresh reports'}
          </button>
          {incidents.length === 0 ? (
            <p>No incident reports match this status.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {incidents.map((incident) => (
                <li
                  className="admin-incident-item"
                  key={incident.id}
                  style={{
                    border: '1px solid #ddd',
                    borderRadius: 8,
                    marginTop: 12,
                    padding: 14,
                  }}
                >
                  <strong>{incident.type.replace(/_/g, ' ')}</strong>
                  <div>
                    {incident.severity} · {incident.status} ·{' '}
                    {incident.source === 'simulation' || incident.source === 'demo'
                      ? 'Simulated'
                      : 'User report'}
                  </div>
                  <div>
                    {incident.latitude.toFixed(5)}, {incident.longitude.toFixed(5)}
                    {incident.road_reference ? ` · ${incident.road_reference}` : ''}
                  </div>
                  {incident.description && <p>{incident.description}</p>}
                  <div>Reported: {new Date(incident.created_at).toLocaleString()}</div>
                  {incident.verified_at && (
                    <div>Verified: {new Date(incident.verified_at).toLocaleString()}</div>
                  )}
                  {incident.ended_at && (
                    <div>Resolved: {new Date(incident.ended_at).toLocaleString()}</div>
                  )}
                  {incident.status === 'reported' && (
                    <>
                    <button
                      type="button"
                      onClick={() => void handleModeration(incident.id, 'verify')}
                      disabled={moderatingId !== null}
                    >
                      {moderatingId === incident.id ? 'Saving...' : 'Verify report'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleModeration(incident.id, 'reject')}
                      disabled={moderatingId !== null}
                      style={{ marginLeft: 8 }}
                    >
                      {moderatingId === incident.id ? 'Saving...' : 'Reject report'}
                    </button>
                    </>
                  )}
                  {incident.status !== 'resolved' && incident.status !== 'rejected' && (
                    <button
                      type="button"
                      onClick={() => void handleModeration(incident.id, 'resolve')}
                      disabled={moderatingId !== null}
                      style={{ marginLeft: 8 }}
                    >
                      {moderatingId === incident.id ? 'Saving...' : 'Resolve report'}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}

export default AdminIncidents
