import { useCallback, useRef, useState } from 'react'
import type { GeolocationStatus } from '../types/routing'

interface UseGeolocationResult {
  latitude: number | null
  longitude: number | null
  accuracy: number | null
  timestamp: number | null
  loading: boolean
  error: string | null
  isWatching: boolean
  status: GeolocationStatus
  startWatching: () => void
  stopWatching: () => void
}

export function useGeolocation(): UseGeolocationResult {
  const [status, setStatus] = useState<GeolocationStatus>('idle')
  const [latitude, setLatitude] = useState<number | null>(null)
  const [longitude, setLongitude] = useState<number | null>(null)
  const [accuracy, setAccuracy] = useState<number | null>(null)
  const [timestamp, setTimestamp] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const watchIdRef = useRef<number | null>(null)

  const startWatching = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setStatus('unsupported')
      setError('This browser does not support geolocation.')
      return
    }

    setStatus('requesting')
    setError(null)

    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setStatus('active')
        setLatitude(pos.coords.latitude)
        setLongitude(pos.coords.longitude)
        setAccuracy(pos.coords.accuracy ?? null)
        setTimestamp(pos.timestamp)
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStatus('denied')
          setError('Location permission was denied.')
        } else if (err.code === err.TIMEOUT) {
          setStatus('unavailable')
          setError('Location request timed out.')
        } else {
          setStatus('unavailable')
          setError('Location is currently unavailable.')
        }
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    )
  }, [])

  const stopWatching = useCallback(() => {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
    setStatus('idle')
  }, [])

  return {
    latitude,
    longitude,
    accuracy,
    timestamp,
    loading: status === 'requesting',
    error,
    isWatching: watchIdRef.current !== null,
    status,
    startWatching,
    stopWatching,
  }
}