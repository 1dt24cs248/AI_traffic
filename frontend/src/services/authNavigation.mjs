const PROTECTED_PATHS = new Set([
  '/home',
  '/dashboard',
  '/map',
  '/admin/incidents',
  '/simulations',
  '/predictions',
  '/alerts',
  '/reports',
])

const DEFAULT_AUTHENTICATED_PATH = '/home'

function asPath(value) {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object' || typeof value.pathname !== 'string') return null

  const search = typeof value.search === 'string' ? value.search : ''
  const hash = typeof value.hash === 'string' ? value.hash : ''
  return `${value.pathname}${search}${hash}`
}

export function getSafeReturnPath(value) {
  const candidate = asPath(value)
  if (!candidate || !candidate.startsWith('/') || candidate.startsWith('//') || candidate.includes('\\')) {
    return DEFAULT_AUTHENTICATED_PATH
  }

  try {
    const parsed = new URL(candidate, 'https://traffic-app.invalid')
    if (parsed.origin !== 'https://traffic-app.invalid' || !PROTECTED_PATHS.has(parsed.pathname)) {
      return DEFAULT_AUTHENTICATED_PATH
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return DEFAULT_AUTHENTICATED_PATH
  }
}

export function getFeatureCardNavigation(path, authenticated) {
  if (authenticated) return { to: path }
  return { to: '/login', state: { from: path } }
}

export function getProtectedRouteLoginState(location) {
  return { from: getSafeReturnPath(location) }
}

export function getPostLoginPath(state) {
  return getSafeReturnPath(state && typeof state === 'object' ? state.from : null)
}

export function getRegistrationLoginState(state) {
  const from = getSafeReturnPath(state && typeof state === 'object' ? state.from : null)
  return { from }
}
