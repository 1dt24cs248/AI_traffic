import api from './api'
import type { AnalyticsFilters } from '../types/analytics'
import type { ReportData } from '../types/reports'

export async function getReport(filters: AnalyticsFilters): Promise<ReportData> {
  const response = await api.get<ReportData>('/api/reports', { params: filters })
  return response.data
}

export function reportErrorMessage(error: unknown): string {
  if (
    typeof error === 'object'
    && error !== null
    && 'response' in error
    && typeof error.response === 'object'
    && error.response !== null
    && 'data' in error.response
    && typeof error.response.data === 'object'
    && error.response.data !== null
    && 'detail' in error.response.data
    && typeof error.response.data.detail === 'string'
  ) {
    return error.response.data.detail
  }
  if (error instanceof Error) return error.message
  return 'Could not load the report.'
}
