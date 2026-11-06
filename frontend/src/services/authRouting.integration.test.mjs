import assert from 'node:assert/strict'

process.env.NODE_ENV = 'production'
const React = (await import('react')).default
const { renderToStaticMarkup } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const { createServer } = await import('vite')

const TOKEN_STORAGE_KEY = 'auth_token'

const values = new Map()
globalThis.localStorage = {
  getItem: (key) => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: (key) => values.delete(key),
}

const vite = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { default: App } = await vite.ssrLoadModule('/src/App.tsx')
  const { default: AppLayout } = await vite.ssrLoadModule('/src/layouts/AppLayout.tsx')
  const renderAt = (path) => renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(App)),
  )
  const renderSidebarAt = (path) => renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(AppLayout)),
  )

  const homeSidebar = renderSidebarAt('/home')
  assert.match(homeSidebar, /<a aria-current="page" class="nav-group-label active" href="\/home">Overview<\/a>/)
  for (const path of ['/dashboard', '/predictions', '/map', '/reports', '/alerts', '/simulations']) {
    const sidebar = renderSidebarAt(path)
    assert.match(sidebar, /<a class="nav-group-label" href="\/home">Overview<\/a>/)
  }
  console.log('PASS mounted sidebar navigation: Overview links to Home and is active only on /home')

  values.delete(TOKEN_STORAGE_KEY)
  const landing = renderAt('/')
  assert.match(landing, /AI Traffic Flow Predictor/)
  assert.match(landing, /Traffic context, with the evidence in view\./)
  assert.equal((landing.match(/class="landing-feature"/g) ?? []).length, 8)
  assert.equal((landing.match(/class="landing-feature" href="\/login"/g) ?? []).length, 8)

  for (const path of [
    '/home',
    '/dashboard',
    '/map',
    '/admin/incidents',
    '/simulations',
    '/predictions',
    '/alerts',
    '/reports',
  ]) {
    const protectedMarkup = renderAt(path)
    assert.doesNotMatch(protectedMarkup, /class="app-sidebar"/, `${path} must not render protected layout without a session`)
    assert.doesNotMatch(protectedMarkup, /Plan my route|Compare routes|Incident moderation/, `${path} must not render protected feature content without a session`)
  }

  values.set(TOKEN_STORAGE_KEY, 'test-session-token')
  const staleSessionMarkup = renderAt('/predictions')
  assert.match(staleSessionMarkup, /Verifying your session/)
  assert.doesNotMatch(staleSessionMarkup, /class="app-sidebar"/, 'feature content stays hidden until the server validates the token')

  console.log('PASS mounted React Router integration: public landing and all feature cards render without a session')
  console.log('PASS mounted React Router integration: every protected route with no token withholds the protected layout')
  console.log('PASS mounted React Router integration: a stored but unvalidated token cannot render protected content')
} finally {
  await vite.close()
}
