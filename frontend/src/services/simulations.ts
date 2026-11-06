import api from './api'
import type {
  SimulationCreateRequest,
  SimulationRunDetail,
  SimulationRunSummary,
} from '../types/simulations'

export async function createSimulation(
  payload: SimulationCreateRequest,
): Promise<SimulationRunSummary> {
  const response = await api.post<SimulationRunSummary>('/api/simulations', payload)
  return response.data
}

export async function getSimulations(): Promise<SimulationRunSummary[]> {
  const response = await api.get<SimulationRunSummary[]>('/api/simulations')
  return response.data
}

export async function getSimulation(runId: string): Promise<SimulationRunDetail> {
  const response = await api.get<SimulationRunDetail>(`/api/simulations/${runId}`)
  return response.data
}

export function extractSimulationError(err: unknown): string {
  const error = err as {
    response?: { data?: { detail?: unknown }; status?: number }
  }
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail !== undefined) return JSON.stringify(detail)
  if (error.response?.status) {
    return `Backend returned status ${error.response.status}.`
  }
  if (err instanceof Error) return err.message
  return 'Unknown error while contacting the backend.'
}
