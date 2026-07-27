import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

/**
 * Catches render-time exceptions so one bad component does not blank the app.
 *
 * Without this, a throw during render unmounts the whole React tree and the
 * operator gets a white page with no indication that anything is wrong — the
 * most extreme form of a UI reporting a failure as if it were a normal state.
 *
 * Deliberately not a data-fetching error state: a request that failed and code
 * that threw are different problems, and a backend outage must not tear down
 * the page chrome the operator needs in order to understand the outage.
 */
export default class ErrorBoundary extends Component<{ children?: ReactNode }, { error: Error | null }> {
  constructor(props: { children?: ReactNode }) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // No telemetry sink in this repo, so the console is the record. Keep the
    // component stack: it is the only way to find which subtree threw.
    console.error('Unhandled render error', error, info?.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div style={{ padding: '2rem', textAlign: 'center' }} role="alert">
        <p style={{ fontWeight: 600 }}>Something broke while rendering this view</p>
        <p style={{ fontSize: '0.8rem', opacity: 0.7 }}>{error.message || String(error)}</p>
        <p style={{ fontSize: '0.8rem', opacity: 0.5 }}>
          This is a bug in the interface, not a problem with your data.
        </p>
        <button type="button" onClick={() => this.setState({ error: null })} style={{ marginTop: '0.75rem' }}>
          Try again
        </button>
      </div>
    )
  }
}
