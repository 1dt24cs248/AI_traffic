import type { RouteSummary, TrafficCoverage } from '../types/routing'

interface RouteCardProps {
  index: number
  route: RouteSummary
  traffic: TrafficCoverage | null
  isSelected: boolean
  onSelect: () => void
}

function RouteCard({ index, route, traffic, isSelected, onSelect }: RouteCardProps) {
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
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Route {index + 1}</div>
      <div style={{ fontSize: 14, color: '#444' }}>Distance: {route.distance_km.toFixed(1)} km</div>
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
          Traffic coverage reported by backend: {traffic.matched_roads.length} matched road(s) within{' '}
          {traffic.match_radius_meters} m
        </div>
      )}
      <button onClick={onSelect} disabled={isSelected} style={{ cursor: isSelected ? 'default' : 'pointer' }}>
        {isSelected ? 'Selected' : 'Select Route'}
      </button>
    </div>
  )
}

export default RouteCard