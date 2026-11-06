import type { IncidentSeverity, IncidentSource, IncidentType } from './incidents'

export type AlertStatus = 'active' | 'resolved'

export interface TrafficAlert {
  id: string
  incident_id: string
  type: IncidentType
  severity: IncidentSeverity
  status: AlertStatus
  latitude: number
  longitude: number
  road_id: string | null
  road_reference: string | null
  description: string | null
  source: IncidentSource
  created_at: string
  verified_at: string | null
  ended_at: string | null
}

export interface AlertFilters {
  status_filter?: 'active' | 'resolved' | 'all'
  severity?: IncidentSeverity
  incident_type?: IncidentType
  start_date?: string
  end_date?: string
}
