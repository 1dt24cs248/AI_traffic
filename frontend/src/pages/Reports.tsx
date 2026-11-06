import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getReport, reportErrorMessage } from '../services/reports'
import { getTrafficSources } from '../services/analytics'
import { getMyIncidents, extractIncidentError } from '../services/incidents'
import type { Incident } from '../types/incidents'
import type { ReportData } from '../types/reports'

function Reports() {
  const [sources, setSources] = useState<string[]>([])
  const [sourcesError, setSourcesError] = useState<string | null>(null)
  const [source, setSource] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [myIncidents, setMyIncidents] = useState<Incident[]>([])
  const [myIncidentsLoading, setMyIncidentsLoading] = useState(true)
  const [myIncidentsError, setMyIncidentsError] = useState<string | null>(null)
  const invalidDateRange = !!(startDate && endDate && startDate > endDate)

  useEffect(() => {
    let active = true
    getTrafficSources()
      .then((result) => {
        if (active) {
          setSources(result)
          setSourcesError(null)
        }
      })
      .catch((requestError: unknown) => {
        if (active) {
          setSources([])
          setSourcesError(reportErrorMessage(requestError))
        }
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    getMyIncidents()
      .then((items) => { if (active) setMyIncidents(items) })
      .catch((requestError: unknown) => {
        if (active) setMyIncidentsError(extractIncidentError(requestError))
      })
      .finally(() => { if (active) setMyIncidentsLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    if (invalidDateRange) {
      setReport(null)
      setLoading(false)
      setError(null)
      return () => { active = false }
    }
    setLoading(true)
    setError(null)
    getReport({
      ...(source ? { source } : {}),
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {}),
    })
      .then((result) => { if (active) setReport(result) })
      .catch((requestError: unknown) => {
        if (active) setError(reportErrorMessage(requestError))
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [source, startDate, endDate, invalidDateRange])

  return (
    <section className="reports-page">
      <h1>Traffic reports</h1>
      <p>
        Report aggregates are queried from stored traffic observations and persisted incident and
        simulation records. Prediction results are not saved by the current application.
      </p>

      <section aria-labelledby="my-incident-reports-heading">
        <h2 id="my-incident-reports-heading">My incident reports</h2>
        <p>Submitted reports are reviewed by an authorized administrator. Only verified, unresolved reports appear as active alerts.</p>
        {myIncidentsLoading && <p role="status">Loading your reports...</p>}
        {!myIncidentsLoading && myIncidentsError && <p role="alert">Your reports could not be loaded: {myIncidentsError}</p>}
        {!myIncidentsLoading && !myIncidentsError && myIncidents.length === 0 && <p>You have not submitted any incident reports.</p>}
        {!myIncidentsLoading && !myIncidentsError && myIncidents.length > 0 && (
          <ul className="incident-report-list">
            {myIncidents.map((incident) => (
              <li key={incident.id}>
                <div className="incident-report-heading">
                  <strong>{incident.type.replace(/_/g, ' ')} · {incident.severity}</strong>
                  <span className={`status-pill status-${incident.status}`}>
                    {incident.status === 'reported' ? 'Pending verification' : incident.status[0].toUpperCase() + incident.status.slice(1)}
                  </span>
                </div>
                <div>{incident.road_reference ?? 'Road not identified'} · {incident.latitude.toFixed(5)}, {incident.longitude.toFixed(5)}</div>
                <small>Submitted {new Date(incident.created_at).toLocaleString()}{incident.verified_at ? ` · Reviewed ${new Date(incident.verified_at).toLocaleString()}` : ''}{incident.ended_at ? ` · Resolved ${new Date(incident.ended_at).toLocaleString()}` : ''}</small>
                {incident.description && <p>{incident.description}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, margin: '16px 0' }}>
        <label>
          Traffic source
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="">All sources</option>
            {sources.map((item) => <option key={item} value={item}>{item}</option>)}
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
      {sourcesError && <p role="alert">Available data sources could not be loaded: {sourcesError}</p>}
      {invalidDateRange && <p role="alert">Start date must be on or before end date.</p>}
      {loading && <p role="status">Loading report data...</p>}
      {!loading && error && <p role="alert">Report could not be loaded: {error}</p>}
      {!loading && report && (
        <>
          <p>
            Traffic metric scope — source: {report.filters.source ?? 'all sources combined'} ·
            observation dates: {report.filters.start_date ?? 'all dates'} to{' '}
            {report.filters.end_date ?? (report.filters.start_date ? 'present' : 'all dates')}
          </p>
          {!report.filters.source && (
            <p role="note" style={{ color: '#854d0e', background: '#fef3c7', padding: 10, borderRadius: 6 }}>
              Traffic metrics combine available sources and may include synthetic simulation observations.
              Choose a specific source to keep its metrics separate.
            </p>
          )}
          <p>
            Source filter applies to traffic observations. Date filter applies to traffic timestamps
            and to incident/simulation creation dates.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            <ReportMetric
              label="Traffic observations"
              value={report.traffic.summary.sample_count.toLocaleString()}
              detail={`${report.traffic.summary.road_count} roads`}
            />
            <ReportMetric
              label="Average speed"
              value={report.traffic.summary.avg_speed === null ? '—' : `${report.traffic.summary.avg_speed.toFixed(1)} km/h`}
              detail="Selected traffic source and observation date range"
            />
            <ReportMetric
              label="Average vehicle count"
              value={report.traffic.summary.avg_vehicle_count?.toFixed(1) ?? '—'}
              detail="Same filtered traffic records"
            />
            <ReportMetric
              label="Incident reports"
              value={String(report.incidents.total)}
              detail={`${report.incidents.active_verified_alert_count} active verified alerts`}
            />
            <ReportMetric
              label="Simulation runs"
              value={String(report.simulation_runs.total)}
              detail={`${report.simulation_runs.records_generated_in_displayed_runs.toLocaleString()} records in displayed runs`}
            />
          </div>

          <section>
            <h2>Daily traffic trend</h2>
            {report.traffic.daily_trend.length === 0 ? (
              <p>No traffic observations in this report period.</p>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={report.traffic.daily_trend}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis label={{ value: 'Average speed (stored units)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="avg_speed" stroke="#2563eb" name="Average speed" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </section>

          <section>
            <h2>Hourly traffic volume</h2>
            {report.traffic.volume_by_hour.length === 0 ? (
              <p>No hourly traffic observations in this report period.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={report.traffic.volume_by_hour}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" label={{ value: 'Hour of day', position: 'insideBottom', offset: -5 }} />
                  <YAxis label={{ value: 'Average vehicle count', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Bar dataKey="avg_vehicle_count" fill="#4f46e5" name="Average vehicle count" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </section>

          <section>
            <h2>Hourly average speed</h2>
            <p>Based on the same selected traffic source and observation date range; speed is stored in km/h.</p>
            {report.traffic.speed_by_hour.length === 0 ? (
              <p>No hourly speed observations in this report period.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={report.traffic.speed_by_hour}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" label={{ value: 'Hour of day', position: 'insideBottom', offset: -5 }} />
                  <YAxis label={{ value: 'Average speed (km/h)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="avg_speed" stroke="#16a34a" name="Average speed (km/h)" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </section>

          <section>
            <h2>Road statistics</h2>
            {report.traffic.road_statistics.length === 0 ? (
              <p>No road-level traffic data in this report period.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th>Road</th><th>Samples</th><th>Average speed (km/h)</th>
                      <th>Minimum speed (km/h)</th><th>Average vehicle count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.traffic.road_statistics.map((road) => (
                      <tr key={road.road_id}>
                        <td>{road.road_name ?? road.road_id}</td>
                        <td>{road.sample_count}</td>
                        <td>{road.avg_speed.toFixed(1)}</td>
                        <td>{road.min_speed.toFixed(1)}</td>
                        <td>{road.avg_vehicle_count.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <h2>Incident summaries</h2>
            <p>By status: {Object.entries(report.incidents.by_status).map(([key, count]) => `${key}: ${count}`).join(' · ') || 'No incident reports'}</p>
            <p>By severity: {Object.entries(report.incidents.by_severity).map(([key, count]) => `${key}: ${count}`).join(' · ') || 'No incident reports'}</p>
            <p className="report-scope-note">
              User reports stay unverified until reviewed. Only verified, unresolved incidents appear in active Alerts.
            </p>
            <h3>Recent incident reports</h3>
            {report.incidents.reports.length === 0 ? (
              <p>No incident reports match this date range.</p>
            ) : (
              <ul className="incident-report-list">
                {report.incidents.reports.map((incident) => (
                  <li key={incident.id}>
                    <div className="incident-report-heading">
                      <strong>{incident.type.replace(/_/g, ' ')} · {incident.severity}</strong>
                      <span className={`status-pill status-${incident.status}`}>
                        {incident.status === 'reported' ? 'Reported · awaiting review' : incident.status}
                      </span>
                    </div>
                    <div>{incident.road_reference ?? incident.road_id ?? 'Road not identified'} · {incident.latitude.toFixed(5)}, {incident.longitude.toFixed(5)}</div>
                    <small>
                      {incident.source === 'simulation' || incident.source === 'demo' ? 'Simulated/demo' : 'User report'}
                      {' · '}Reported {new Date(incident.created_at).toLocaleString()}
                      {incident.verified_at ? ` · Verified ${new Date(incident.verified_at).toLocaleString()}` : ''}
                      {incident.ended_at ? ` · Resolved ${new Date(incident.ended_at).toLocaleString()}` : ''}
                    </small>
                    {incident.description && <p>{incident.description}</p>}
                  </li>
                ))}
              </ul>
            )}
            {report.incidents.total > report.incidents.displayed_reports && (
              <p>Showing the {report.incidents.displayed_reports} most recent reports of {report.incidents.total} in this date range.</p>
            )}
          </section>

          <section>
            <h2>Simulation runs</h2>
            {report.simulation_runs.runs.length === 0 ? (
              <p>No simulation runs were created in this report period.</p>
            ) : (
              <ul>
                {report.simulation_runs.runs.map((run) => (
                  <li key={run.id}>
                    {run.name} — {run.scenario_type}, {run.record_count} synthetic records,
                    {' '}{new Date(run.created_at).toLocaleString()}
                  </li>
                ))}
              </ul>
            )}
            {report.simulation_runs.displayed < report.simulation_runs.total && (
              <p>Showing the most recent {report.simulation_runs.displayed} of {report.simulation_runs.total} runs.</p>
            )}
          </section>

          {!report.prediction_history.available && (
            <p>{report.prediction_history.reason}</p>
          )}
        </>
      )}
    </section>
  )
}

function ReportMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="report-metric">
      <div>{label}</div>
      <strong style={{ display: 'block', fontSize: 22, margin: '8px 0' }}>{value}</strong>
      <small>{detail}</small>
    </div>
  )
}

export default Reports
