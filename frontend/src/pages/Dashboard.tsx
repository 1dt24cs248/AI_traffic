import { useEffect, useState, useCallback } from 'react'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import SectionCard from '../components/SectionCard'
import {
  getVolumeByHour,
  getSpeedByHour,
  getWeekdayVsWeekend,
  getRoadStatistics,
  getPeakHours,
  getCongestionHeatmap,
  extractErrorMessage,
} from '../services/analytics'
import type {
  VolumeByHourItem,
  SpeedByHourItem,
  WeekdayVsWeekend,
  RoadStatistic,
  PeakHourItem,
  CongestionHeatmapCell,
} from '../types/analytics'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

function initialState<T>(): AsyncState<T> {
  return { data: null, loading: true, error: null }
}

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] // day_of_week 0=Monday, matches backend

function mean(values: number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
}

function Dashboard() {
  const [volume, setVolume] = useState<AsyncState<VolumeByHourItem[]>>(initialState)
  const [speed, setSpeed] = useState<AsyncState<SpeedByHourItem[]>>(initialState)
  const [weekdayWeekend, setWeekdayWeekend] = useState<AsyncState<WeekdayVsWeekend>>(initialState)
  const [roadStats, setRoadStats] = useState<AsyncState<RoadStatistic[]>>(initialState)
  const [peakHours, setPeakHours] = useState<AsyncState<PeakHourItem[]>>(initialState)
  const [heatmap, setHeatmap] = useState<AsyncState<CongestionHeatmapCell[]>>(initialState)

  const fetchAll = useCallback(() => {
    // Each section fetches and fails independently (Promise, not Promise.all) so
    // one failing endpoint never blocks the others from loading/displaying.
    setVolume(initialState())
    getVolumeByHour()
      .then((data) => setVolume({ data, loading: false, error: null }))
      .catch((err) => setVolume({ data: null, loading: false, error: extractErrorMessage(err) }))

    setSpeed(initialState())
    getSpeedByHour()
      .then((data) => setSpeed({ data, loading: false, error: null }))
      .catch((err) => setSpeed({ data: null, loading: false, error: extractErrorMessage(err) }))

    setWeekdayWeekend(initialState())
    getWeekdayVsWeekend()
      .then((data) => setWeekdayWeekend({ data, loading: false, error: null }))
      .catch((err) => setWeekdayWeekend({ data: null, loading: false, error: extractErrorMessage(err) }))

    setRoadStats(initialState())
    getRoadStatistics()
      .then((data) => setRoadStats({ data, loading: false, error: null }))
      .catch((err) => setRoadStats({ data: null, loading: false, error: extractErrorMessage(err) }))

    setPeakHours(initialState())
    getPeakHours()
      .then((data) => setPeakHours({ data, loading: false, error: null }))
      .catch((err) => setPeakHours({ data: null, loading: false, error: extractErrorMessage(err) }))

    setHeatmap(initialState())
    getCongestionHeatmap()
      .then((data) => setHeatmap({ data, loading: false, error: null }))
      .catch((err) => setHeatmap({ data: null, loading: false, error: extractErrorMessage(err) }))
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  // Summary card values - all computed from real fetched arrays, nothing invented.
  const avgSpeedOverall = speed.data ? mean(speed.data.map((d) => d.avg_speed)) : null
  const avgVehicleCountOverall = volume.data ? mean(volume.data.map((d) => d.avg_vehicle_count)) : null
  const topPeakHour = peakHours.data && peakHours.data.length > 0 ? peakHours.data[0] : null
  const roadsMonitored = roadStats.data ? roadStats.data.length : null

  // Weekday vs weekend chart data - only includes sides that actually have data,
  // never plots a fabricated 0 for a null side.
  const weekdayWeekendChartData: { name: string; avg_speed: number; avg_vehicle_count: number }[] = []
  if (weekdayWeekend.data?.weekday) {
    weekdayWeekendChartData.push({ name: 'Weekday', ...weekdayWeekend.data.weekday })
  }
  if (weekdayWeekend.data?.weekend) {
    weekdayWeekendChartData.push({ name: 'Weekend', ...weekdayWeekend.data.weekend })
  }

  // Heatmap: lookup by "day_hour" key, and a min/max speed range computed from the
  // ACTUAL returned cells (not a fixed assumed scale) for color interpolation.
  const heatmapLookup = new Map<string, CongestionHeatmapCell>()
  let heatmapMinSpeed = Infinity
  let heatmapMaxSpeed = -Infinity
  if (heatmap.data) {
    for (const cell of heatmap.data) {
      heatmapLookup.set(`${cell.day_of_week}_${cell.hour}`, cell)
      if (cell.avg_speed < heatmapMinSpeed) heatmapMinSpeed = cell.avg_speed
      if (cell.avg_speed > heatmapMaxSpeed) heatmapMaxSpeed = cell.avg_speed
    }
  }

  function heatmapCellColor(speedValue: number): string {
    if (heatmapMaxSpeed === heatmapMinSpeed) return 'hsl(120, 60%, 50%)'
    const ratio = (speedValue - heatmapMinSpeed) / (heatmapMaxSpeed - heatmapMinSpeed) // 0=slowest, 1=fastest
    const hue = ratio * 120 // 0=red (congested), 120=green (free-flow)
    return `hsl(${hue}, 65%, 50%)`
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div>
          <h1 style={{ margin: 0 }}>Traffic Dashboard</h1>
          <p style={{ color: '#666', marginTop: 4 }}>
            Traffic analytics computed from the simulation dataset stored in PostgreSQL.
          </p>
        </div>
        <button onClick={fetchAll} style={{ padding: '8px 16px', cursor: 'pointer' }}>
          Refresh
        </button>
      </div>

      <div
        style={{
          display: 'inline-block',
          padding: '4px 12px',
          borderRadius: 12,
          backgroundColor: '#eef2ff',
          color: '#3730a3',
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 20,
        }}
      >
        Data source: Simulation
      </div>

      {/* Summary cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <SummaryCard
          label="Average Speed"
          value={avgSpeedOverall !== null ? `${avgSpeedOverall.toFixed(1)} km/h` : '—'}
        />
        <SummaryCard
          label="Average Vehicle Count"
          value={avgVehicleCountOverall !== null ? avgVehicleCountOverall.toFixed(1) : '—'}
        />
        <SummaryCard
          label="Peak Traffic Hour"
          value={topPeakHour ? `${topPeakHour.hour}:00 (${topPeakHour.avg_speed.toFixed(1)} km/h)` : '—'}
        />
        <SummaryCard label="Monitored Roads" value={roadsMonitored !== null ? String(roadsMonitored) : '—'} />
      </div>

      {/* Volume by hour */}
      <SectionCard
        title="Traffic Volume by Hour"
        loading={volume.loading}
        error={volume.error}
        isEmpty={!!volume.data && volume.data.length === 0}
      >
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={volume.data ?? []}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="hour" label={{ value: 'Hour', position: 'insideBottom', offset: -5 }} />
            <YAxis label={{ value: 'Vehicle count', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Bar dataKey="avg_vehicle_count" fill="#4f46e5" name="Avg vehicle count" />
          </BarChart>
        </ResponsiveContainer>
      </SectionCard>

      {/* Speed by hour */}
      <SectionCard
        title="Average Speed by Hour"
        loading={speed.loading}
        error={speed.error}
        isEmpty={!!speed.data && speed.data.length === 0}
      >
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={speed.data ?? []}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="hour" label={{ value: 'Hour', position: 'insideBottom', offset: -5 }} />
            <YAxis label={{ value: 'Speed (km/h)', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Line type="monotone" dataKey="avg_speed" stroke="#16a34a" name="Avg speed" />
          </LineChart>
        </ResponsiveContainer>
      </SectionCard>

      {/* Weekday vs weekend */}
      <SectionCard
        title="Weekday vs Weekend"
        loading={weekdayWeekend.loading}
        error={weekdayWeekend.error}
        isEmpty={weekdayWeekendChartData.length === 0}
      >
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={weekdayWeekendChartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="avg_speed" fill="#16a34a" name="Avg speed" />
            <Bar dataKey="avg_vehicle_count" fill="#4f46e5" name="Avg vehicle count" />
          </BarChart>
        </ResponsiveContainer>
        {weekdayWeekendChartData.length === 1 && (
          <p style={{ color: '#888', fontSize: 13, marginTop: 8 }}>
            Only {weekdayWeekendChartData[0].name.toLowerCase()} data is currently available in this dataset.
          </p>
        )}
      </SectionCard>

      {/* Road statistics */}
      <SectionCard
        title="Road Statistics"
        loading={roadStats.loading}
        error={roadStats.error}
        isEmpty={!!roadStats.data && roadStats.data.length === 0}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '2px solid #eee' }}>
              <th style={{ padding: 8 }}>Road ID</th>
              <th style={{ padding: 8 }}>Road Name</th>
              <th style={{ padding: 8 }}>Avg Speed</th>
              <th style={{ padding: 8 }}>Min Speed</th>
              <th style={{ padding: 8 }}>Avg Vehicle Count</th>
              <th style={{ padding: 8 }}>Sample Count</th>
            </tr>
          </thead>
          <tbody>
            {(roadStats.data ?? []).map((road) => (
              <tr key={road.road_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: 8 }}>{road.road_id}</td>
                <td style={{ padding: 8 }}>{road.road_name ?? '—'}</td>
                <td style={{ padding: 8 }}>{road.avg_speed.toFixed(1)}</td>
                <td style={{ padding: 8 }}>{road.min_speed.toFixed(1)}</td>
                <td style={{ padding: 8 }}>{road.avg_vehicle_count.toFixed(1)}</td>
                <td style={{ padding: 8 }}>{road.sample_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      {/* Peak hours */}
      <SectionCard
        title="Peak Hours"
        loading={peakHours.loading}
        error={peakHours.error}
        isEmpty={!!peakHours.data && peakHours.data.length === 0}
      >
        <ul style={{ paddingLeft: 20 }}>
          {(peakHours.data ?? []).map((item) => (
            <li key={item.hour} style={{ marginBottom: 4 }}>
              Hour {item.hour}:00 — average speed {item.avg_speed.toFixed(1)} km/h
            </li>
          ))}
        </ul>
      </SectionCard>

      {/* Congestion heatmap */}
      <SectionCard
        title="Congestion Heatmap"
        loading={heatmap.loading}
        error={heatmap.error}
        isEmpty={!!heatmap.data && heatmap.data.length === 0}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ padding: 4 }}></th>
                {Array.from({ length: 24 }, (_, hour) => (
                  <th key={hour} style={{ padding: 2, fontSize: 10, fontWeight: 400 }}>
                    {hour}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DAY_LABELS.map((label, dayIndex) => (
                <tr key={label}>
                  <td style={{ padding: 4, fontSize: 12, fontWeight: 600 }}>{label}</td>
                  {Array.from({ length: 24 }, (_, hour) => {
                    const cell = heatmapLookup.get(`${dayIndex}_${hour}`)
                    return (
                      <td
                        key={hour}
                        title={cell ? `${cell.avg_speed.toFixed(1)} km/h (n=${cell.sample_count})` : 'No data'}
                        style={{
                          width: 16,
                          height: 16,
                          backgroundColor: cell ? heatmapCellColor(cell.avg_speed) : '#f0f0f0',
                          border: '1px solid #fff',
                        }}
                      />
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ color: '#888', fontSize: 12, marginTop: 8 }}>
          Green = faster / less congested, Red = slower / more congested (scale relative to this dataset's own
          observed speed range). Gray cells indicate no data for that day/hour combination.
        </p>
      </SectionCard>
    </div>
  )
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        border: '1px solid #e0e0e0',
        borderRadius: 8,
        padding: 16,
        backgroundColor: '#fff',
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
      }}
    >
      <div style={{ fontSize: 13, color: '#888', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: '#1a1a2e' }}>{value}</div>
    </div>
  )
}

export default Dashboard