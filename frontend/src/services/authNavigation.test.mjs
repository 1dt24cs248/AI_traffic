import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import {
  getFeatureCardNavigation,
  getPostLoginPath,
  getProtectedRouteLoginState,
  getRegistrationLoginState,
  getSafeReturnPath,
} from './authNavigation.mjs'

const cases = []
const test = (name, run) => cases.push({ name, run })

test('public landing route remains outside the authenticated route group', async () => {
  const app = await readFile(new URL('../App.tsx', import.meta.url), 'utf8')
  const landing = await readFile(new URL('../pages/LandingPage.tsx', import.meta.url), 'utf8')
  assert.match(app, /<Route path="\/" element={<LandingPage \/>} \/>/)
  assert.match(app, /<Route path="\/login" element={<Login \/>} \/>/)
  assert.match(app, /<Route path="\/register" element={<Register \/>} \/>/)
  assert.match(landing, /<section id="about" className="landing-section landing-about" aria-label="Project overview">/)
  const overview = landing.match(/<section id="about"[\s\S]*?<\/section>/)?.[0]
  assert.ok(overview, 'the public overview section exists')
  assert.doesNotMatch(overview, /<Link|<a\b|<button|onClick=/)
})

test('landing cards, protected-route guard, and login submit use the tested navigation policy', async () => {
  const [landing, guard, login] = await Promise.all([
    readFile(new URL('../pages/LandingPage.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../components/ProtectedRoute.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../pages/Login.tsx', import.meta.url), 'utf8'),
  ])
  assert.match(landing, /getFeatureCardNavigation\(href, isAuthenticated\(\)\)/)
  assert.match(guard, /if \(!isAuthenticated\(\)\)/)
  assert.match(guard, /<Navigate to="\/login" state=\{getProtectedRouteLoginState\(location\)\}/)
  assert.match(login, /await login\(email, password\)[\s\S]*navigate\(getPostLoginPath\(location\.state\)/)
  assert.match(guard, /getCurrentUser\(\)[\s\S]*setSessionState\('authenticated'\)[\s\S]*setSessionState\('unauthenticated'\)/)
})

test('feature destinations match unique protected routes in the application router', async () => {
  const [app, landing] = await Promise.all([
    readFile(new URL('../App.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../pages/LandingPage.tsx', import.meta.url), 'utf8'),
  ])
  const protectedGroup = app.match(/<Route element={<ProtectedRoute \/>}>[\s\S]*?<\/Route>\s*<Route path="\*"/)?.[0]
  assert.ok(protectedGroup, 'protected routes are grouped under ProtectedRoute before the wildcard')
  const protectedPaths = [...protectedGroup.matchAll(/<Route path="([^"]+)"/g)].map((match) => match[1])
  const featurePaths = [...landing.matchAll(/\['\d{2}',\s*'[^']+',\s*'[^']+',\s*'([^']+)'\]/g)].map((match) => match[1])
  assert.equal(featurePaths.length, 8)
  assert.equal(new Set(protectedPaths).size, protectedPaths.length, 'protected route paths are unique')
  for (const path of featurePaths) {
    assert.ok(protectedPaths.includes(path), `feature path ${path} is protected`)
    assert.equal([...app.matchAll(new RegExp(`<Route path="${path.replaceAll('/', '\\/')}"`, 'g'))].length, 1, `${path} is defined once`)
  }
})

test('logged-out feature cards lead to login with their protected destination', () => {
  assert.deepEqual(getFeatureCardNavigation('/predictions', false), {
    to: '/login',
    state: { from: '/predictions' },
  })
})

test('authenticated feature cards open the selected feature directly', () => {
  assert.deepEqual(getFeatureCardNavigation('/map', true), { to: '/map' })
})

test('direct protected navigation preserves path, query, and hash through login', () => {
  const loginState = getProtectedRouteLoginState({
    pathname: '/dashboard',
    search: '?range=week',
    hash: '#traffic',
  })
  assert.deepEqual(loginState, { from: '/dashboard?range=week#traffic' })
  assert.equal(getPostLoginPath(loginState), '/dashboard?range=week#traffic')
})

test('login without a valid destination uses the existing authenticated default', () => {
  assert.equal(getPostLoginPath(null), '/home')
  assert.equal(getPostLoginPath({ from: '/unknown' }), '/home')
})

test('external and malformed return URLs cannot redirect away from the app', () => {
  for (const candidate of [
    'https://attacker.invalid',
    '//attacker.invalid/path',
    '///attacker.invalid/path',
    '/\\attacker.invalid/path',
    '/%2f%2fattacker.invalid/path',
  ]) {
    assert.equal(getSafeReturnPath(candidate), '/home', candidate)
    assert.equal(getPostLoginPath({ from: candidate }), '/home', candidate)
  }
})

test('registration preserves the intended route for the existing separate-login flow', () => {
  const state = getRegistrationLoginState({ from: '/simulations' })
  assert.deepEqual(state, { from: '/simulations' })
  assert.equal(getPostLoginPath(state), '/simulations')
})

test('administrator destination remains a protected internal return route', () => {
  assert.equal(getSafeReturnPath('/admin/incidents'), '/admin/incidents')
})

test('administrator navigation and moderation still check the authenticated role', async () => {
  const [layout, moderation] = await Promise.all([
    readFile(new URL('../layouts/AppLayout.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../pages/AdminIncidents.tsx', import.meta.url), 'utf8'),
  ])
  assert.match(layout, /user\.role === 'ADMIN'/)
  assert.match(layout, /adminAccess === 'allowed'.*NavLink to="\/admin\/incidents"/s)
  assert.match(moderation, /currentUser\.role !== 'ADMIN'/)
})

let failures = 0
for (const { name, run } of cases) {
  try {
    await run()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures += 1
    console.error(`FAIL ${name}: ${error?.stack ?? error}`)
  }
}
console.log(`${cases.length - failures}/${cases.length} authentication-navigation tests passed`)
if (failures) process.exitCode = 1
