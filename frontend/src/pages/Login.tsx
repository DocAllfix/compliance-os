import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme';
import { ApiError } from '@/lib/api';
import { BrandLogo } from '@/components/BrandLogo';

export function Login() {
  const { login } = useAuth();
  const { toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      const from = (location.state as { from?: string } | null)?.from ?? '/dashboard';
      navigate(from, { replace: true });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Login failed. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        background: 'var(--bg-page)',
        position: 'relative',
      }}
    >
      {/* Left: brand panel (navy, mirrors the Amisys identity lockup) */}
      <aside
        style={{
          background: 'var(--brand-navy)',
          padding: '64px 56px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <BrandLogo size={38} />
          <div>
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 26,
                fontWeight: 600,
                color: 'var(--on-navy)',
                lineHeight: 1,
              }}
            >
              Amisys
            </div>
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: '0.12em',
                color: 'var(--on-navy-muted)',
                marginTop: 4,
              }}
            >
              qhse
            </div>
          </div>
        </div>

        <div style={{ maxWidth: '40ch' }}>
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 22,
              fontWeight: 500,
              lineHeight: 1.45,
              color: 'var(--on-navy)',
              marginBottom: 16,
            }}
          >
            "Read your documents the way an assessor would, then tell you what's missing in plain English."
          </p>
          <p
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 13,
              color: 'var(--on-navy-muted)',
              letterSpacing: '0.02em',
            }}
          >
            ISO 9001 · 14001 · 45001
          </p>
        </div>

        <div
          style={{
            fontSize: 11,
            color: 'var(--on-navy-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          Amisys QHSE v0.1 · Five Rise Consultancy
        </div>
      </aside>

      {/* Right: form */}
      <main
        style={{
          padding: '64px 56px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          style={{ position: 'absolute', top: 24, right: 24 }}
        >
          <svg className="icon icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
          <svg className="icon icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2" /><path d="M12 20v2" /><path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" /><path d="M2 12h2" /><path d="M20 12h2" /><path d="m4.93 19.07 1.41-1.41" /><path d="m17.66 6.34 1.41-1.41" /></svg>
        </button>

        <form onSubmit={submit} style={{ width: '100%', maxWidth: 380 }}>
          <h1
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 32,
              fontWeight: 600,
              lineHeight: 1.1,
              letterSpacing: '-0.012em',
              marginBottom: 8,
            }}
          >
            Welcome back
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 13.5,
              color: 'var(--text-tertiary)',
              marginBottom: 32,
            }}
          >
            Sign in to review your compliance analyses.
          </p>

          <div className="field-grid" style={{ gridTemplateColumns: '1fr', gap: 18, marginBottom: 8 }}>
            <div className="field full">
              <label className="field-label" htmlFor="username">Username</label>
              <input
                id="username"
                className="input"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="field full">
              <label className="field-label" htmlFor="password">Password</label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>

          {error && (
            <div
              style={{
                marginTop: 12,
                padding: '10px 12px',
                background: 'var(--severity-major-bg)',
                color: 'var(--severity-major-fg)',
                borderRadius: 6,
                fontSize: 12.5,
                lineHeight: 1.45,
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-accent"
            disabled={loading}
            style={{ marginTop: 24, width: '100%', justifyContent: 'center', padding: '10px 16px' }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </main>
    </div>
  );
}
