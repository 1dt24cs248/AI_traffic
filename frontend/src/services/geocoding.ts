import api from './api'
import type { GeocodingSearchResponse } from '../types/routing'

export async function searchPlaces(
  query: string,
): Promise<GeocodingSearchResponse> {
  const response = await api.get<GeocodingSearchResponse>(
    '/api/geocoding/search',
    {
      params: {
        q: query,
      },
    },
  )

  return response.data
}

export function extractGeocodingError(err: unknown): string {
  const error = err as any

  if (error?.response) {
    const detail = error.response.data?.detail

    if (typeof detail === 'string') {
      return detail
    }

    if (error.response.status === 401) {
      return 'Your session has expired. Please log in again.'
    }

    if (error.response.status === 422) {
      return 'Enter at least 2 characters to search.'
    }

    if (error.response.status === 429) {
      return 'Place search is temporarily busy. Please try again shortly.'
    }

    if (error.response.status === 502) {
      return 'The place-search service is temporarily unavailable.'
    }

    if (error.response.status === 504) {
      return 'Place search timed out. Please try again.'
    }

    return `Place search failed (status ${error.response.status}).`
  }

  if (error?.request) {
    return 'Could not reach the backend. Is it running?'
  }

  return 'Place search failed.'
}