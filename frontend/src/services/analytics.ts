import api from './api'
import type {
  VolumeByHourItem,
  SpeedByHourItem,
  WeekdayVsWeekend,
  RoadStatistic,
  PeakHourItem,
  CongestionHeatmapCell,
} from '../types/analytics'

// Reuses the existing `api` Axios instance from ./api — it already attaches the
// JWT Authorization header via its request interceptor. No second client here.

const SIMULATION_SOURCE = 'simulation'

export async function getVolumeByHour(source: string = SIMULATION_SOURCE): Promise<VolumeByHourItem[]> {
  const response = await api.get<VolumeByHourItem[]>('/api/analytics/volume-by-hour', {
    params: { source },
  })
  return response.data
}

export async function getSpeedByHour(source: string = SIMULATION_SOURCE): Promise<SpeedByHourItem[]> {
  const response = await api.get<SpeedByHourItem[]>('/api/analytics/speed-by-hour', {
    params: { source },
  })
  return response.data
}

export async function getWeekdayVsWeekend(source: string = SIMULATION_SOURCE): Promise<WeekdayVsWeekend> {
  const response = await api.get<WeekdayVsWeekend>('/api/analytics/weekday-vs-weekend', {
    params: { source },
  })
  return response.data
}

export async function getRoadStatistics(source: string = SIMULATION_SOURCE): Promise<RoadStatistic[]> {
  const response = await api.get<RoadStatistic[]>('/api/analytics/road-statistics', {
    params: { source },
  })
  return response.data
}

export async function getPeakHours(
  source: string = SIMULATION_SOURCE,
  topN?: number,
): Promise<PeakHourItem[]> {
  const response = await api.get<PeakHourItem[]>('/api/analytics/peak-hours', {
    params: { source, ...(topN ? { top_n: topN } : {}) },
  })
  return response.data
}

export async function getCongestionHeatmap(source: string = SIMULATION_SOURCE): Promise<CongestionHeatmapCell[]> {
  const response = await api.get<CongestionHeatmapCell[]>('/api/analytics/congestion-heatmap', {
    params: { source },
  })
  return response.data
}

export function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return 'Unknown error while contacting the backend.'
}