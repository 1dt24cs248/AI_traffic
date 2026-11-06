import api from './api'
import type {
  VolumeByHourItem,
  SpeedByHourItem,
  WeekdayVsWeekend,
  RoadStatistic,
  PeakHourItem,
  CongestionHeatmapCell,
  AnalyticsFilters,
  TrafficSummary,
} from '../types/analytics'

// Reuses the existing `api` Axios instance from ./api — it already attaches the
// JWT Authorization header via its request interceptor. No second client here.

export async function getTrafficSources(): Promise<string[]> {
  const response = await api.get<string[]>('/api/analytics/sources')
  return response.data
}

export async function getTrafficSummary(filters: AnalyticsFilters): Promise<TrafficSummary> {
  const response = await api.get<TrafficSummary>('/api/analytics/summary', { params: filters })
  return response.data
}

export async function getVolumeByHour(filters: AnalyticsFilters = {}): Promise<VolumeByHourItem[]> {
  const response = await api.get<VolumeByHourItem[]>('/api/analytics/volume-by-hour', {
    params: filters,
  })
  return response.data
}

export async function getSpeedByHour(filters: AnalyticsFilters = {}): Promise<SpeedByHourItem[]> {
  const response = await api.get<SpeedByHourItem[]>('/api/analytics/speed-by-hour', {
    params: filters,
  })
  return response.data
}

export async function getWeekdayVsWeekend(filters: AnalyticsFilters = {}): Promise<WeekdayVsWeekend> {
  const response = await api.get<WeekdayVsWeekend>('/api/analytics/weekday-vs-weekend', {
    params: filters,
  })
  return response.data
}

export async function getRoadStatistics(filters: AnalyticsFilters = {}): Promise<RoadStatistic[]> {
  const response = await api.get<RoadStatistic[]>('/api/analytics/road-statistics', {
    params: filters,
  })
  return response.data
}

export async function getPeakHours(
  filters: AnalyticsFilters = {},
  topN?: number,
): Promise<PeakHourItem[]> {
  const response = await api.get<PeakHourItem[]>('/api/analytics/peak-hours', {
    params: { ...filters, ...(topN ? { top_n: topN } : {}) },
  })
  return response.data
}

export async function getCongestionHeatmap(
  filters: AnalyticsFilters = {},
): Promise<CongestionHeatmapCell[]> {
  const response = await api.get<CongestionHeatmapCell[]>('/api/analytics/congestion-heatmap', {
    params: filters,
  })
  return response.data
}

export function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return 'Unknown error while contacting the backend.'
}