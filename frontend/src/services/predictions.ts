import api from './api'
import type {
  PEMS08CongestionPrediction,
  PEMS08Features,
  PEMS08SpeedPrediction,
  PEMS08Status,
} from '../types/predictions'

export async function getPEMS08Status(): Promise<PEMS08Status> {
  const response = await api.get<PEMS08Status>('/api/predictions/pems08/status')
  return response.data
}

export async function predictPEMS08Speed(
  features: PEMS08Features,
): Promise<PEMS08SpeedPrediction> {
  const response = await api.post<PEMS08SpeedPrediction>(
    '/api/predictions/pems08/speed',
    features,
  )
  return response.data
}

export async function predictPEMS08Congestion(
  features: PEMS08Features,
): Promise<PEMS08CongestionPrediction> {
  const response = await api.post<PEMS08CongestionPrediction>(
    '/api/predictions/pems08/congestion',
    features,
  )
  return response.data
}

export function predictionErrorMessage(error: unknown): string {
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
  return 'Prediction request failed.'
}
