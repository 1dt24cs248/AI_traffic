export interface VolumeByHourItem {
  hour: number
  avg_vehicle_count: number
  sample_count: number
}

export interface SpeedByHourItem {
  hour: number
  avg_speed: number
  sample_count: number
}

export interface WeekdayWeekendStats {
  avg_speed: number
  avg_vehicle_count: number
  sample_count: number
}

export interface WeekdayVsWeekend {
  weekday: WeekdayWeekendStats | null
  weekend: WeekdayWeekendStats | null
}

export interface RoadStatistic {
  road_id: string
  road_name: string | null
  avg_speed: number
  min_speed: number
  avg_vehicle_count: number
  sample_count: number
}

export interface PeakHourItem {
  hour: number
  avg_speed: number
}

export interface CongestionHeatmapCell {
  day_of_week: number
  hour: number
  avg_speed: number
  sample_count: number
}