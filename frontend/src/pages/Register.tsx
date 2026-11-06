import { FormEvent, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { register } from '../services/auth'
import { getRegistrationLoginState } from '../services/authNavigation.mjs'

function Register() {
  const navigate = useNavigate()
  const location = useLocation()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await register({ email, full_name: fullName, password })
      navigate('/login', { replace: true, state: getRegistrationLoginState(location.state) })
    } catch (err) {
      setError('Registration failed. The email may already be registered, or the password may be too short.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-card">
        <p className="auth-brand">AI Traffic Flow Predictor</p>
        <h1>Create your account</h1>
        <p className="auth-description">Get started with route planning and traffic insights.</p>
        <form className="auth-form" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="fullName">Full name</label>
          <br />
          <input
            id="fullName"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="email">Email</label>
          <br />
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <br />
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </div>
        {error && <p role="alert" className="auth-error">{error}</p>}
        <button className="auth-submit" type="submit" disabled={loading}>
          {loading ? 'Registering...' : 'Register'}
        </button>
      </form>
      <p className="auth-footer">
        Already have an account? <Link to="/login" state={getRegistrationLoginState(location.state)}>Login</Link>
      </p>
      </section>
    </div>
  )
}

export default Register
