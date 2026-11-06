import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getTrafficSources, getTrafficSummary } from '../services/analytics'
import { getReport, reportErrorMessage } from '../services/reports'
import type { TrafficSummary } from '../types/analytics'
import type { ReportData } from '../types/reports'

interface SourceSummary {
  source: string
  summary: TrafficSummary | null
  error: string | null
}

function Home() {
  const [sourceSummaries, setSourceSummaries] = useState<SourceSummary[]>([])
  const [trafficLoading, setTrafficLoading] = useState(true)
  const [trafficError, setTrafficError] = useState<string | null>(null)
  const [report, setReport] = useState<ReportData | null>(null)
  const [reportLoading, setReportLoading] = useState(true)
  const [reportError, setReportError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getTrafficSources()
      .then(async (sources) => {
        const summaries = await Promise.all(
          sources.map(async (source): Promise<SourceSummary> => {
            try {
              return { source, summary: await getTrafficSummary({ source }), error: null }
            } catch (error) {
              return {
                source,
                summary: null,
                error: error instanceof Error ? error.message : 'Could not load this source.',
              }
            }
          }),
        )
        if (active) {
          setSourceSummaries(summaries)
          setTrafficError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setTrafficError(error instanceof Error ? error.message : 'Could not load traffic sources.')
          setSourceSummaries([])
        }
      })
      .finally(() => {
        if (active) setTrafficLoading(false)
      })

    getReport({})
      .then((data) => { if (active) setReport(data) })
      .catch((error: unknown) => {
        if (active) setReportError(reportErrorMessage(error))
      })
      .finally(() => {
        if (active) setReportLoading(false)
      })

    return () => { active = false }
  }, [])

  return (
    <div className="home-overview">
      <section className="home-overview-hero">
        <p style={{ margin: '0 0 8px', color: '#4338ca', fontWeight: 700 }}>
          AI Traffic Flow Predictor
        </p>
        <h1 style={{ margin: '0 0 12px' }}>
          A clearer view of your trip and the data behind it.
        </h1>
        <p style={{ maxWidth: 760, color: '#475569' }}>
          This project combines stored traffic observations, synthetic simulations, incident
          reporting, and OSRM road routes. Source labels are shown separately; route times are
          OSRM estimates, not live traffic predictions.
        </p>
        <Link className="button button-primary" to="/predictions">Plan my route <span aria-hidden="true">→</span></Link>
      </section>

      <section aria-labelledby="home-traffic-heading">
        <h2 id="home-traffic-heading">Stored traffic by source</h2>
        <p>
          Each source is summarized independently. These are stored observations, not a live traffic
          feed; the latest timestamp below is the newest observation available for that source.
        </p>
        {trafficLoading && <p role="status">Loading traffic summaries...</p>}
        {!trafficLoading && trafficError && (
          <p role="alert">Traffic summaries could not be loaded: {trafficError}</p>
        )}
        {!trafficLoading && !trafficError && sourceSummaries.length === 0 && (
          <p>No traffic sources or observations are currently available.</p>
        )}
        {!trafficLoading && sourceSummaries.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 14 }}>
            {sourceSummaries.map(({ source, summary, error }) => (
              <article className="home-source-card" key={source}>
                <h3 style={{ margin: '0 0 10px' }}>{source}</h3>
                {error && <p role="alert">Summary unavailable: {error}</p>}
                {!error && summary && summary.sample_count === 0 && <p>No observations for this source.</p>}
                {!error && summary && summary.sample_count > 0 && (
                  <>
                    <p style={{ margin: '4px 0' }}>
                      {summary.sample_count.toLocaleString()} observations · {summary.road_count} roads
                    </p>
                    <p style={{ margin: '4px 0' }}>
                      Average stored speed: {summary.avg_speed === null ? '—' : `${summary.avg_speed.toFixed(1)} km/h`}
                    </p>
                    <p style={{ margin: '8px 0 0', color: '#526078', fontSize: 13 }}>
                      Latest observation:{' '}
                      {summary.last_observation
                        ? new Date(summary.last_observation).toLocaleString()
                        : 'timestamp unavailable'}
                    </p>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="home-features-heading">
        <h2 id="home-features-heading">Project features</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
          <FeatureLink to="/dashboard" title="Traffic dashboard" description="Filter and explore stored observations by source and date." />
          <FeatureLink to="/predictions" title="SmartCommute AI" description="Compare route options with sampled traffic, provider weather, and reported incidents." />
          <FeatureLink to="/map" title="Map & routing" description="Open the interactive map, compare routes, and report a road hazard." />
          <FeatureLink to="/simulations" title="Traffic simulations" description="Generate and inspect clearly labeled synthetic scenarios for demonstrations." />
          <FeatureLink to="/alerts" title="Verified alerts" description="Review active and resolved verified incident alerts." />
          <FeatureLink to="/reports" title="Reports" description="Review traffic, incident, and simulation summaries." />
        </div>
      </section>

      <section aria-labelledby="home-activity-heading">
        <h2 id="home-activity-heading">Current records</h2>
        {reportLoading && <p role="status">Loading incident and simulation summaries...</p>}
        {!reportLoading && reportError && (
          <p role="alert">Incident and simulation summaries could not be loaded: {reportError}</p>
        )}
        {!reportLoading && report && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
            <SummaryTile label="Incident reports" value={report.incidents.total.toLocaleString()} />
            <SummaryTile label="Active verified alerts" value={report.incidents.active_verified_alert_count.toLocaleString()} />
            <SummaryTile label="Saved simulation runs" value={report.simulation_runs.total.toLocaleString()} />
          </div>
        )}
      </section>

      <p style={{ color: '#64748b', fontSize: 13 }}>
        PEMS08 predictions are not currently connected to local application-road observations or
        route ranking. Simulated records are not sent to the PEMS08 model.
      </p>
    </div>
  )
}

function FeatureLink({ to, title, description }: { to: string; title: string; description: string }) {
  return (
    <Link
      to={to}
      className="home-feature-link"
    >
      <strong>{title}</strong>
      <div>{description}</div>
    </Link>
  )
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="home-summary-tile">
      <div>{label}</div>
      <strong>{value}</strong>
    </div>
  )
}

export default Home
