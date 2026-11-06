export interface SimulationCreateRequest {
  name: string
  duration_minutes: number
  interval_minutes: number
  seed: number
  scenario_type: 'baseline'
  start_time?: string
}

export interface SimulationRunSummary {
  id: string
  name: string
  scenario_type: string
  created_at: string
  duration_minutes: number
  interval_minutes: number
  seed: number
  record_count: number
  road_count: number
  source: 'simulation'
  status: 'completed'
  start_time: string
  end_time: string
}

export interface SimulationRunDetail extends SimulationRunSummary {
  parameters: Record<string, unknown>
  road_ids_affected: string[]
  scenario_snapshot: {
    limitations?: string[]
    roads?: Array<{
      road_id: string
      road_name: string
      record_count: number
      average_speed_kmh: number
      average_vehicle_count: number
    }>
    [key: string]: unknown
  }
  notes: string
}
