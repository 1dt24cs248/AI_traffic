export type IncidentType =
  | 'fallen_tree'
  | 'road_closure'
  | 'accident'
  | 'construction'
  | 'waterlogging'
  | 'broken_vehicle'
  | 'obstruction'
  | 'partial_obstruction'
  | 'other'

export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical'
export type IncidentStatus = 'reported' | 'verified' | 'rejected' | 'resolved'
export type IncidentSource = 'user_report' | 'system' | 'simulation' | 'demo'

export interface Incident {
  id: string
  type: IncidentType
  latitude: number
  longitude: number
  road_id: string | null
  road_reference: string | null
  severity: IncidentSeverity
  status: IncidentStatus
  source: IncidentSource
  verified: boolean
  confidence: number | null
  started_at: string
  ended_at: string | null
  verified_at: string | null
  verified_by: string | null
  description: string | null
  created_at: string
  updated_at: string
  created_by: string | null
}

export interface IncidentCreate {
  type: IncidentType
  latitude: number
  longitude: number
  severity: IncidentSeverity
  road_reference?: string
  description?: string
}
