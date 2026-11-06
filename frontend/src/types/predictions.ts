export interface PEMS08Features {
  flow: number
  occupancy: number
  speed: number
  flow_lag_5m: number
  flow_lag_15m: number
  flow_lag_30m: number
  flow_lag_1h: number
  speed_lag_5m: number
  speed_lag_15m: number
  speed_lag_30m: number
  speed_lag_1h: number
  occupancy_lag_5m: number
  occupancy_lag_15m: number
  occupancy_lag_30m: number
  occupancy_lag_1h: number
  hour: number
  day_of_week: number
  month: number
  is_weekend: number
  is_rush_hour: number
}

export interface PEMS08Status {
  dataset: string
  prediction_horizon: string
  speed_model_available: boolean
  congestion_model_available: boolean
  feature_count: number
  features: string[]
  limitations: string[]
}

export interface PEMS08SpeedPrediction {
  model: string
  prediction_horizon: string
  predicted_speed: number
  speed_unit_note: string
}

export interface PEMS08CongestionPrediction {
  model: string
  prediction_horizon: string
  congestion_level: string
  probabilities: Record<string, number>
  probability_note: string
}
