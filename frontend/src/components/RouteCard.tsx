import type { RouteSummary, TrafficCoverage } from '../types/routing'

interface RouteCardProps {
  index: number
  route: RouteSummary
  traffic: TrafficCoverage | null
  isSelected: boolean
  onSelect: () => void
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

function RouteCard({ index, route, traffic, isSelected, onSelect }: RouteCardProps) {
  const aiTraffic = route.ai_traffic

  return (
    <div
      style={{
        border: isSelected ? '2px solid #4f46e5' : '1px solid #e0e0e0',
        borderRadius: 8,
        padding: 14,
        marginBottom: 10,
        backgroundColor: isSelected ? '#eef2ff' : '#fff',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>
        Route {index + 1}
      </div>

      <div style={{ fontSize: 14, color: '#444' }}>
        Distance: {route.distance_km.toFixed(1)} km
      </div>

      <div style={{ fontSize: 14, color: '#444', marginBottom: 6 }}>
        Estimated routing duration (OSRM): {Math.round(route.duration_minutes)} min
      </div>

      {traffic && traffic.traffic_coverage === false && (
        <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>
          AI traffic data unavailable for this route
        </div>
      )}

      {traffic && traffic.traffic_coverage === true && (
        <div style={{ fontSize: 12, color: '#555', marginBottom: 6 }}>
          Traffic coverage reported by backend: {traffic.matched_roads.length} matched
          road(s) within {traffic.match_radius_meters} m
        </div>
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
        disabled={isSelected}
        style={{
          cursor: isSelected ? 'default' : 'pointer',
          marginTop: 10,
        }}
      >
        {isSelected ? 'Selected' : 'Select Route'}
      </button>
    </div>
  )
}

export default RouteCard