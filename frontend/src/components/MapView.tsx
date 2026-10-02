import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'

const OPENFREEMAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty'

interface MapViewProps {
  onMapReady: (map: maplibregl.Map) => void
  onLoadError: (message: string) => void
}

function MapView({ onMapReady, onLoadError }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    maplibregl.setWorkerUrl(maplibreWorkerUrl)

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OPENFREEMAP_STYLE_URL,
      center: [78.9629, 20.5937],
      zoom: 4,
      attributionControl: { compact: false },
    })

    mapRef.current = map

    map.on('load', () => {
      onMapReady(map)
    })

    map.on('error', (e) => {
      onLoadError(e.error?.message || 'Failed to load the map.')
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}

export default MapView