import type { RouteTrafficResult, RouteSummary, TrafficCoverage } from '../types/routing'

interface RouteCardProps {
  index: number
  route: RouteSummary
  traffic: TrafficCoverage | null
  currentFlow?: RouteTrafficResult | null
  currentFlowLoading?: boolean
  currentFlowError?: string | null
  showCurrentTraffic?: boolean
  isSelected: boolean
  isRecommended: boolean
  onSelect: () => void
  onEstimate?: () => void
}

function formatNumber(value: number | null, suffix: string): string {
  return value === null ? 'unavailable' : `${value.toFixed(1)}${suffix}`
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'unavailable'
}

function weatherCodeLabel(code: number): string {
  if (code === 0) return 'clear'
  if (code <= 3) return 'cloudy'
  if (code === 45 || code === 48) return 'fog'
  if (code >= 51 && code <= 67) return 'drizzle/rain'
  if (code >= 71 && code <= 77) return 'snow'
  if (code >= 80 && code <= 82) return 'rain showers'
  if (code >= 85 && code <= 86) return 'snow showers'
  if (code >= 95) return 'thunderstorm'
  return `weather code ${code}`
}

function getCongestionLabel(level: string | null): string {
  if (!level) return 'Unavailable'

  switch (level) {
    case 'LOW':
      return 'Low'
    case 'MEDIUM':
      return 'Medium'
    case 'HIGH':
      return 'High'
    case 'SEVERE':
      return 'Severe'
    default:
      return level
  }
}

function getCongestionSymbol(level: string | null): string {
  switch (level) {
    case 'LOW':
      return '🟢'
    case 'MEDIUM':
      return '🟡'
    case 'HIGH':
      return '🟠'
    case 'SEVERE':
      return '🔴'
    default:
      return '⚪'
  }
}

function RouteCard({ index, route, traffic, currentFlow, currentFlowLoading, currentFlowError, showCurrentTraffic, isSelected, isRecommended, onSelect, onEstimate }: RouteCardProps) {
  const aiTraffic = route.ai_traffic

  return (
    <article className={`route-card${isSelected ? ' is-selected' : ''}${!route.feasible ? ' is-blocked' : ''}`}>
      <div className="route-card-heading">
        <div className="route-card-title">
        Route {index + 1}{isRecommended ? ' — Recommended' : ''}
        </div>
        <div className="route-card-metrics" aria-label="Route estimate">
          <span><strong>{Math.round(route.duration_minutes)} min</strong><small>OSRM estimate</small></span>
          <span><strong>{route.distance_km.toFixed(1)} km</strong><small>Distance</small></span>
        </div>
      </div>
      <p className="route-card-method">Travel time is an OSRM estimate and does not include live traffic.</p>
      {route.comparison_score !== null && route.comparison_score !== undefined && (
        <div style={{ fontSize: 13, marginBottom: 6 }}>
          Rule-based comparison score: <strong>{route.comparison_score.toFixed(1)}/100</strong>
          {' '}(not an AI prediction)
        </div>
      )}

      {!route.feasible && (
        <div role="alert" style={{ color: '#b00020', fontSize: 13, marginBottom: 8 }}>
          Not feasible: {route.infeasibility_reason ?? 'A verified road closure affects this route.'}
        </div>
      )}

      {route.incident_warnings && route.incident_warnings.length > 0 && (
        <div style={{ margin: '8px 0', padding: 8, backgroundColor: '#fff7ed', borderRadius: 6 }}>
          <strong style={{ fontSize: 13 }}>Relevant incident reports</strong>
          {route.incident_warnings.map((warning) => (
            <div key={warning.incident_id} style={{ fontSize: 12, marginTop: 5 }}>
              <div>
                {warning.type.replace(/_/g, ' ')} · {warning.severity} ·{' '}
                {warning.source === 'simulation' || warning.source === 'demo'
                  ? 'Simulated'
                  : warning.verified
                    ? 'Verified'
                    : 'Unverified report'}
              </div>
              <div>
                {warning.distance_meters.toFixed(1)} m from route · {warning.match_basis}
              </div>
              {warning.description && <div>{warning.description}</div>}
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 12, color: '#555', marginBottom: 6 }}>
        PEMS08 AI prediction: unavailable for this Bengaluru route.
        {route.ai_traffic?.data_source === 'simulation'
          ? ' Nearby synthetic observation coverage was found, but it is not used as a prediction.'
          : ' No compatible local prediction is available.'}
      </div>
      {(showCurrentTraffic ?? isSelected) && (
        <section aria-label="Current road traffic" style={{ margin: '8px 0', padding: 9, background: currentFlow && currentFlow.checked_point_count > 0 ? '#f0fdf4' : '#f8fafc', borderRadius: 6 }}>
          <strong style={{ fontSize: 13 }}>Current road traffic · TomTom</strong>
          {currentFlowLoading && <div role="status" style={{ fontSize: 12 }}>Checking sampled road segments on this route…</div>}
          {currentFlowError && <div role="status" style={{ fontSize: 12 }}>{currentFlowError}</div>}
          {!currentFlowLoading && !currentFlowError && !currentFlow && (
            <div role="status" style={{ fontSize: 12 }}>Current traffic samples are unavailable.</div>
          )}
          {currentFlow && (
            <>
              <div style={{ fontSize: 12, marginTop: 5 }}>
                Successfully checked {currentFlow.checked_point_count} of {currentFlow.sampled_point_count} sampled points ({currentFlow.status} coverage).
              </div>
              {currentFlow.reason && <div role="status" style={{ fontSize: 12 }}>{currentFlow.reason}</div>}
              {currentFlow.points.map((point, pointIndex) => {
                const flow = point.flow
                return (
                  <div key={pointIndex} style={{ fontSize: 12, marginTop: 6, paddingTop: 5, borderTop: '1px solid #d1fae5' }}>
                    <strong>Sample {pointIndex + 1}</strong>{' '}
                    {flow ? <>near {flow.latitude.toFixed(4)}, {flow.longitude.toFixed(4)} · current {formatNumber(flow.current_speed, ' km/h')} · free-flow {formatNumber(flow.free_flow_speed, ' km/h')} · confidence {flow.confidence === null ? 'unavailable' : `${(flow.confidence * 100).toFixed(0)}%`} · closure {flow.road_closure === null ? 'unavailable' : flow.road_closure ? 'yes' : 'no'} · retrieved {formatTimestamp(flow.retrieved_at)}{flow.observation_time ? ` · provider observation ${formatTimestamp(flow.observation_time)}` : ''}</> : <>{point.reason ?? 'Traffic data unavailable'}.</>}
                  </div>
                )
              })}
              <div style={{ fontSize: 11, color: '#526078', marginTop: 5 }}>TomTom segment samples are point checks only. They do not cover every road or provide a complete route-wide traffic measurement.</div>
            </>
          )}
          <div style={{ fontSize: 11, color: '#526078' }}>
            Current observed segment flow is separate from the OSRM route ETA, weather comparison, and future AI predictions.
          </div>
        </section>
      )}
      {traffic?.traffic_coverage && (
        <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>
          Across all alternatives, {traffic.matched_roads.length} local synthetic road record(s)
          matched within {traffic.match_radius_meters} m; this is coverage, not traffic flow.
        </div>
      )}

      {route.weather && (
        <section style={{ margin: '8px 0', padding: 9, background: '#f0f9ff', borderRadius: 6 }}>
          <strong style={{ fontSize: 13 }}>
            Weather along route — {route.weather.provider} ({route.weather.status})
          </strong>
          {route.weather.status !== 'unavailable' && (
            <>
              <div style={{ fontSize: 12, marginTop: 5 }}>
                Forecast window: {formatTimestamp(route.weather.forecast_start)} to{' '}
                {formatTimestamp(route.weather.forecast_end)}
              </div>
              <div style={{ fontSize: 12 }}>
                Sampled locations with forecasts: {route.weather.covered_location_count}/
                {route.weather.sampled_location_count}
              </div>
              <div style={{ fontSize: 12, marginTop: 5 }}>
                Mean forecast temperature: {formatNumber(route.weather.avg_temperature_c, ' °C')}
                {' · '}mean hourly precipitation: {formatNumber(route.weather.avg_precipitation_mm_per_hour, ' mm/h')}
                {' · '}rain: {formatNumber(route.weather.avg_rain_mm_per_hour, ' mm/h')}
                {' · '}mean wind: {formatNumber(route.weather.avg_wind_speed_kmh, ' km/h')}
                {' · '}peak gust: {formatNumber(route.weather.max_wind_gusts_kmh, ' km/h')}
                {' · '}peak snowfall: {formatNumber(route.weather.max_snowfall_mm_per_hour, ' mm/h')}
              </div>
              {route.weather.weather_exposure_index !== null && (
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  Rule-based forecast exposure index: {route.weather.weather_exposure_index}/100
                  {' '}(comparison aid only, not a safety rating)
                </div>
              )}
              {route.weather.locations.map((location) => (
                <div
                  key={`${location.latitude},${location.longitude}`}
                  style={{ marginTop: 6, paddingTop: 5, borderTop: '1px solid #dbeafe', fontSize: 11 }}
                >
                  <strong>Current conditions near {location.latitude.toFixed(3)}, {location.longitude.toFixed(3)}:</strong>
                  {' '}{formatNumber(location.current_temperature_c, ' °C')}
                  {location.current_weather_code !== null
                    ? `, ${weatherCodeLabel(location.current_weather_code)}`
                    : ''}
                  {' · '}precipitation {formatNumber(location.current_precipitation_mm, ' mm')}
                  {' · '}wind {formatNumber(location.current_wind_speed_kmh, ' km/h')}
                  {' · '}provider current timestamp {formatTimestamp(location.current_time)}
                </div>
              ))}
            </>
          )}
          <div style={{ fontSize: 11, marginTop: 5, color: '#526078' }}>
            Forecast data retrieved: {formatTimestamp(route.weather.retrieved_at)}.{' '}
            {route.weather.reason}
          </div>
          {route.weather.stale && (
            <div role="status" style={{ fontSize: 12, color: '#92400e', fontWeight: 600 }}>
              Showing a cached forecast. It was not used to rank this route because a fresh
              provider response was unavailable.
            </div>
          )}
          <div style={{ fontSize: 11, color: '#526078' }}>
            Forecast provider: <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a>
            {' '}· CC-BY 4.0 attribution.
          </div>
          <div style={{ fontSize: 11, color: '#526078' }}>
            Forecasts and current conditions are provider model data for sampled locations, not
            roadside measurements. Rainfall alone is not treated as evidence of flooding.
          </div>
        </section>
      )}

      {/* AI Traffic Assessment */}
      {aiTraffic && aiTraffic.status === 'available' && (
        <div
          style={{
            marginTop: 10,
            padding: 12,
            borderRadius: 8,
            backgroundColor: '#f8fafc',
            border: '1px solid #dbeafe',
          }}
        >
          <div
            style={{
              fontWeight: 700,
              marginBottom: 8,
              fontSize: 14,
            }}
          >
            🤖 AI Traffic Analysis
          </div>

          <div style={{ fontSize: 14, marginBottom: 6 }}>
            {getCongestionSymbol(aiTraffic.congestion_level)}{' '}
            <strong>Congestion:</strong>{' '}
            {getCongestionLabel(aiTraffic.congestion_level)}
          </div>

          {aiTraffic.predicted_speed !== null && (
            <div style={{ fontSize: 13, marginBottom: 4 }}>
              Predicted speed: {aiTraffic.predicted_speed.toFixed(2)}
            </div>
          )}

          {aiTraffic.route_score !== null && (
            <div style={{ fontSize: 13, marginBottom: 6 }}>
              AI route score: <strong>{aiTraffic.route_score}/100</strong>
            </div>
          )}

          {aiTraffic.congestion_probabilities && (
            <div style={{ fontSize: 12, marginBottom: 8 }}>
              <div>
                Severe:{' '}
                {((aiTraffic.congestion_probabilities.SEVERE ?? 0) * 100).toFixed(1)}%
              </div>
              <div>
                High:{' '}
                {((aiTraffic.congestion_probabilities.HIGH ?? 0) * 100).toFixed(1)}%
              </div>
              <div>
                Medium:{' '}
                {((aiTraffic.congestion_probabilities.MEDIUM ?? 0) * 100).toFixed(1)}%
              </div>
              <div>
                Low:{' '}
                {((aiTraffic.congestion_probabilities.LOW ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
          )}

          {aiTraffic.road_id && (
            <div style={{ fontSize: 12, color: '#555', marginBottom: 3 }}>
              Matched road: {aiTraffic.road_id}
            </div>
          )}

          {aiTraffic.observation_timestamp && (
            <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
              Observation: {new Date(aiTraffic.observation_timestamp).toLocaleString()}
            </div>
          )}
          {aiTraffic.roads_assessed > 0 && aiTraffic.road_assessments.length > 0 && (
  <div
    style={{
      marginTop: 8,
      marginBottom: 8,
      padding: 10,
      borderRadius: 6,
      backgroundColor: '#f1f5f9',
      border: '1px solid #e2e8f0',
    }}
  >
    <div
      style={{
        fontSize: 13,
        fontWeight: 700,
        marginBottom: 8,
      }}
    >
      Roads assessed by AI: {aiTraffic.roads_assessed}
    </div>

    {aiTraffic.road_assessments.map((road) => (
      <div
        key={road.road_id}
        style={{
          padding: 8,
          marginBottom: 6,
          borderRadius: 5,
          backgroundColor: '#fff',
          border: '1px solid #e5e7eb',
        }}
      >
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            marginBottom: 4,
          }}
        >
          {road.road_id}
        </div>

        <div style={{ fontSize: 12, color: '#555' }}>
          Distance from route: {road.distance_meters.toFixed(1)} m
        </div>

        <div style={{ fontSize: 12, color: '#555' }}>
          Congestion: {getCongestionLabel(road.congestion_level)}
        </div>

        {road.predicted_speed !== null && (
          <div style={{ fontSize: 12, color: '#555' }}>
            Predicted speed: {road.predicted_speed.toFixed(2)}
          </div>
        )}

        {road.route_score !== null && (
          <div style={{ fontSize: 12, color: '#555' }}>
            Score: {road.route_score}/100
          </div>
        )}
      </div>
    ))}
  </div>
)}

          <div
            style={{
              fontSize: 11,
              color: '#92400e',
              backgroundColor: '#fffbeb',
              padding: 7,
              borderRadius: 5,
            }}
          >
            Simulation-based AI estimate.
            <br />
            Not a validated real-world traffic forecast.
          </div>
        </div>
      )}

      {aiTraffic && aiTraffic.status !== 'available' && (
        <div
          style={{
            marginTop: 8,
            padding: 8,
            borderRadius: 6,
            backgroundColor: '#f8fafc',
            color: '#666',
            fontSize: 12,
          }}
        >
          AI traffic prediction unavailable for this route.
          <br />
          {aiTraffic.reason}
        </div>
      )}

      <button
        onClick={onSelect}
        disabled={isSelected || !route.feasible}
        style={{
          cursor: isSelected || !route.feasible ? 'default' : 'pointer',
          marginTop: 10,
        }}
      >
        {!route.feasible ? 'Route blocked' : isSelected ? 'Selected' : 'Select Route'}
      </button>
      {onEstimate && (
        <button type="button" onClick={onEstimate} disabled={currentFlowLoading} style={{ marginLeft: 8, marginTop: 10 }}>
          {currentFlowLoading ? 'Loading traffic samples…' : 'Estimate fuel & energy'}
        </button>
      )}
    </article>
  )
}

export default RouteCard
