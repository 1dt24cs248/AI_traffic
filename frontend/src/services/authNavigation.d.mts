export interface InternalLocation {
  pathname: string
  search?: string
  hash?: string
}

export interface FeatureCardNavigation {
  to: string
  state?: { from: string }
}

export function getSafeReturnPath(value: string | InternalLocation | null | undefined): string
export function getFeatureCardNavigation(path: string, authenticated: boolean): FeatureCardNavigation
export function getProtectedRouteLoginState(location: InternalLocation): { from: string }
export function getPostLoginPath(state: unknown): string
export function getRegistrationLoginState(state: unknown): { from: string }
