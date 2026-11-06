export type FuelVehicle = 'petrol-car' | 'diesel-car' | 'petrol-two-wheeler' | 'ev'

export interface FuelImpactEstimate {
  vehicle: FuelVehicle
  distance_km: number
  energy_unit: 'L' | 'kWh'
  baseline: number
  additional: number | null
  total: number | null
  additional_cost: number | null
  additional_battery_percent: number | null
  estimated_remaining_charge_percent: number | null
  sample_count: number
  reduced_count: number
  heavy_reduction_count: number
  severe_reduction_count: number
  categories: string[]
  average_speed_deficit: number | null
  traffic_latest_retrieved_at: string | null
  traffic_latest_observation_at: string | null
  traffic_coverage: string
  weather_adjustment_applied: false
  weather_adjustment_reason: string
  idling_estimate: null
  formula: string
  limitations: string
}
