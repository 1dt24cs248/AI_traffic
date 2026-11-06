import type { IncidentSource, IncidentStatus } from './incidents'

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

// ---------------------------------------------------------------------------
// Vehicle types supported by the backend routing service.
// car / motorcycle / scooter / truck use OSRM 'driving' profile.
// bicycle uses OSRM 'cycling' profile.
// The backend returns vehicle_profile_note when the profile is approximate.
// ---------------------------------------------------------------------------
export type VehicleType = 'car' | 'motorcycle' | 'scooter' | 'bicycle' | 'truck'

export interface RouteRequest {
  origin_lat: number
  origin_lon: number
  destination_lat: number
  destination_lon: number
  alternatives: boolean
  traffic_match_radius_meters: number
  /** Vehicle type — controls OSRM routing profile. Defaults to 'car'. */
  vehicle_type?: VehicleType
  /** Route preference — 'fastest' (default) or 'shortest'. */
  route_preference?: 'fastest' | 'shortest'
  /** Forecast window anchor; OSRM duration remains a baseline estimate. */
  departure_datetime?: string
  /** Radius in metres within which an incident is flagged on this route. */
  incident_match_radius_meters?: number
  /** Previous recommendation index supplied during an explicit route refresh. */
  previous_recommended_index?: number | null
}

export interface RouteGeometry {
  type: 'LineString'
  coordinates: [number, number][] // [longitude, latitude]
}

export interface CurrentTrafficFlow {
  latitude: number
  longitude: number
  current_speed: number | null
  free_flow_speed: number | null
  current_travel_time_seconds: number | null
  confidence: number | null
  road_closure: boolean | null
  source: string
  observation_time: string | null
  retrieved_at: string
}

export interface RouteTrafficPoint { status: string; flow: CurrentTrafficFlow | null; latitude: number | null; longitude: number | null; reason: string | null }
export interface RouteTrafficResult { status: 'available' | 'partial' | 'unavailable'; sampled_point_count: number; checked_point_count: number; points: RouteTrafficPoint[]; reason: string | null }

export type RouteTrafficStatus =
  | 'available'
  | 'unavailable_no_coverage'
  | 'unavailable_insufficient_history'
  | 'unavailable_incompatible_input'
  | 'unavailable_prediction_error'

export type CongestionLevel =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'SEVERE'

export interface RouteTrafficRoadAssessment {
  road_id: string
  distance_meters: number
  observation_timestamp: string | null
  predicted_speed: number | null
  congestion_level: CongestionLevel | null
  congestion_probabilities: Record<string, number> | null
  route_score: number | null
  status: RouteTrafficStatus
  reason: string
}

export interface RouteTrafficAssessment {
  status: RouteTrafficStatus
  data_source: string | null
  road_id: string | null
  observation_timestamp: string | null
  predicted_speed: number | null
  congestion_level: CongestionLevel | null
  congestion_probabilities: Record<string, number> | null
  route_score: number | null
  roads_assessed: number
  road_assessments: RouteTrafficRoadAssessment[]
  reason: string
}

/** A non-blocking incident near this route (Phase 5+). */
export interface IncidentWarning {
  incident_id: string
  type: string
  severity: string
  status: IncidentStatus
  source: IncidentSource
  verified: boolean
  distance_meters: number
  description: string | null
  road_reference: string | null
  match_basis: string
}

export interface RouteSummary {
  distance_meters: number
  distance_km: number
  duration_seconds: number
  duration_minutes: number
  geometry: RouteGeometry
  ai_traffic?: RouteTrafficAssessment | null
  /** False when a confirmed road closure makes this route infeasible. */
  feasible?: boolean
  infeasibility_reason?: string | null
  /** Non-blocking incidents near this route (populated in Phase 5). */
  incident_warnings?: IncidentWarning[]
  /** Non-null when the OSRM profile is approximate for the selected vehicle. */
  vehicle_profile_note?: string | null
  weather?: RouteWeatherAssessment | null
  /** Rule-based route comparison score, not a model prediction. */
  comparison_score?: number | null
}

export interface WeatherLocationAssessment {
  latitude: number
  longitude: number
  forecast_hours: number
  current_time: string | null
  current_temperature_c: number | null
  current_weather_code: number | null
  current_precipitation_mm: number | null
  current_rain_mm: number | null
  current_wind_speed_kmh: number | null
  current_wind_gusts_kmh: number | null
  avg_precipitation_mm_per_hour: number | null
  avg_rain_mm_per_hour: number | null
  avg_wind_speed_kmh: number | null
  max_wind_gusts_kmh: number | null
  max_snowfall_mm_per_hour: number | null
  weather_codes: number[]
  missing_variables: string[]
}

export interface RouteWeatherAssessment {
  status: 'available' | 'partial' | 'unavailable'
  provider: string
  stale: boolean
  retrieved_at: string | null
  forecast_start: string | null
  forecast_end: string | null
  sampled_location_count: number
  covered_location_count: number
  avg_temperature_c: number | null
  avg_precipitation_mm_per_hour: number | null
  avg_rain_mm_per_hour: number | null
  avg_wind_speed_kmh: number | null
  max_wind_gusts_kmh: number | null
  max_snowfall_mm_per_hour: number | null
  weather_exposure_index: number | null
  locations: WeatherLocationAssessment[]
  reason: string
}

export interface TrafficCoverage {
  traffic_coverage: boolean
  matched_roads: MatchedTrafficRoad[]
  match_radius_meters: number
}

export interface MatchedTrafficRoad {
  road_id: string
  distance_meters: number
}

export interface RouteResponse {
  provider: string
  routes: RouteSummary[]
  traffic: TrafficCoverage
  /** 0-based index of the recommended route. Null if no feasible route. */
  recommended_index?: number | null
  /** 0-based index of the fastest route (lowest OSRM duration). */
  fastest_index?: number
  /** 0-based index of the shortest route (lowest distance). */
  shortest_index?: number
  /** Plain-English explanation of how the recommendation was chosen. */
  ranking_basis?: string
  /** Present when a refresh changes the previously recommended route. */
  recommendation_change_reason?: string | null
  /** Vehicle type used for this request. */
  vehicle_type?: VehicleType
  /** OSRM profile used (driving / cycling / foot). */
  osrm_profile?: string
  comparison_method?: string
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
