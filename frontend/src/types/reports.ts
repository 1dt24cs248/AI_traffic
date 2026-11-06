import type { RoadStatistic, TrafficSummary } from './analytics'

export interface ReportRunSummary {
  id: string
  name: string
  scenario_type: string
  created_at: string
  duration_minutes: number
  record_count: number
  source: 'simulation'
}

export interface ReportData {
  filters: {
    source: string | null
    start_date: string | null
    end_date: string | null
    source_applies_to: string
    date_range_applies_to: string[]
  }
  traffic: {
    summary: TrafficSummary
    road_statistics: RoadStatistic[]
    volume_by_hour: { hour: number; avg_vehicle_count: number; sample_count: number }[]
    speed_by_hour: { hour: number; avg_speed: number; sample_count: number }[]
    daily_trend: {
      date: string
      avg_speed: number
      avg_vehicle_count: number
      sample_count: number
    }[]
  }
  incidents: {
    total: number
    by_status: Record<string, number>
    by_severity: Record<string, number>
    active_verified_alert_count: number
    displayed_reports: number
    reports: IncidentReportSummary[]
  }
  simulation_runs: {
    total: number
    displayed: number
    records_generated_in_displayed_runs: number
    runs: ReportRunSummary[]
  }
  prediction_history: {
    available: boolean
    reason: string
  }
}

export interface IncidentReportSummary {
  id: string
  type: string
  latitude: number
  longitude: number
  road_id: string | null
  road_reference: string | null
  severity: string
  status: 'reported' | 'verified' | 'resolved'
  source: string
  verified: boolean
  description: string | null
  created_at: string
  verified_at: string | null
  ended_at: string | null
}
