import { useCallback, useEffect, useRef, useState } from 'react'
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
  getCurrentLocation: () => Promise<{ latitude: number; longitude: number } | null>
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
    if (watchIdRef.current !== null) return
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
        if (watchIdRef.current !== null) {
          navigator.geolocation.clearWatch(watchIdRef.current)
          watchIdRef.current = null
        }
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

  const getCurrentLocation = useCallback(() => new Promise<{ latitude: number; longitude: number } | null>((resolve) => {
    if (!('geolocation' in navigator)) {
      setStatus('unsupported')
      setError('This browser does not support geolocation.')
      resolve(null)
      return
    }
    setStatus('requesting')
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setStatus('active')
        setLatitude(pos.coords.latitude)
        setLongitude(pos.coords.longitude)
        setAccuracy(pos.coords.accuracy ?? null)
        setTimestamp(pos.timestamp)
        resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude })
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStatus('denied')
          setError('Location permission was denied. You can search for a place instead.')
        } else if (err.code === err.TIMEOUT) {
          setStatus('unavailable')
          setError('Location request timed out. Try again or search for a place.')
        } else {
          setStatus('unavailable')
          setError('Location is currently unavailable. Search for a place instead.')
        }
        resolve(null)
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    )
  }), [])

  const stopWatching = useCallback(() => {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
    setStatus('idle')
  }, [])

  useEffect(() => () => {
    if (watchIdRef.current !== null && 'geolocation' in navigator) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
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
    getCurrentLocation,
    stopWatching,
  }
}
