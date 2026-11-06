import api from './api'
import type { Incident, IncidentCreate } from '../types/incidents'
import { extractErrorMessage } from './routing'

export async function getIncidents(
  status?: Incident['status'],
  includeResolved = false,
): Promise<Incident[]> {
  const response = await api.get<Incident[]>('/api/incidents', {
    params: {
      ...(status ? { status } : {}),
      ...(includeResolved ? { include_resolved: true } : {}),
    },
  })
  return response.data
}

export async function getMyIncidents(): Promise<Incident[]> {
  const response = await api.get<Incident[]>('/api/incidents/mine')
  return response.data
}

export async function createIncident(payload: IncidentCreate): Promise<Incident> {
  const response = await api.post<Incident>('/api/incidents', payload)
  return response.data
}

export async function verifyIncident(incidentId: string): Promise<Incident> {
  const response = await api.post<Incident>(`/api/incidents/${incidentId}/verify`)
  return response.data
}

export async function rejectIncident(incidentId: string): Promise<Incident> {
  const response = await api.post<Incident>(`/api/incidents/${incidentId}/reject`)
  return response.data
}

export async function resolveIncident(incidentId: string): Promise<Incident> {
  const response = await api.post<Incident>(`/api/incidents/${incidentId}/resolve`)
  return response.data
}

export { extractErrorMessage as extractIncidentError }
