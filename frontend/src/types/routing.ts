export type GeolocationStatus =
  | 'idle'
  | 'requesting'
  | 'active'
  | 'denied'
  | 'unavailable'
  | 'unsupported'

export interface GeoPosition {
  latitude: number
  longitude: number
  accuracy: number | null
  timestamp: number
}

export type OriginMode = 'current' | 'manual'

export interface RouteRequest {
  origin_lat: number
  origin_lon: number
  destination_lat: number
  destination_lon: number
  alternatives: boolean
  traffic_match_radius_meters: number
}

export interface RouteGeometry {
  type: 'LineString'
  coordinates: [number, number][] // [longitude, latitude]
}

export interface RouteSummary {
  distance_meters: number
  distance_km: number
  duration_seconds: number
  duration_minutes: number
  geometry: RouteGeometry
}

export interface TrafficCoverage {
  traffic_coverage: boolean
  matched_roads: unknown[]
  match_radius_meters: number
}

export interface RouteResponse {
  provider: string
  routes: RouteSummary[]
  traffic: TrafficCoverage
}
export type DestinationMode = 'search' | 'manual'

export interface GeocodingResult {
  display_name: string
  latitude: number
  longitude: number
  type: string | null
  category: string | null
}

export interface GeocodingSearchResponse {
  query: string
  results: GeocodingResult[]
  attribution: string
}