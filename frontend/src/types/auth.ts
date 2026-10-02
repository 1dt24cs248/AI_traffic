export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface RegisterRequest {
  email: string
  full_name: string
  password: string
}

export interface RegisterResponse {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
}