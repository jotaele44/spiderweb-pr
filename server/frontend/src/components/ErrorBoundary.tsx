import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Shown instead of the default panel. Receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time throws so one broken module does not blank the whole app.
 *
 * React unmounts the entire tree when a render throws with no boundary above it,
 * which in a single-page workbench means a white screen and no way back short of
 * a reload. This keeps the chrome usable and offers a reset.
 *
 * Class component because `componentDidCatch` has no hook equivalent.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  reset = (): void => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <section className="panel">
        <div className="empty-state" role="alert">
          <h2>Something went wrong</h2>
          <p className="desc">{error.message}</p>
          <button className="act" onClick={this.reset}>
            RETRY
          </button>
        </div>
      </section>
    );
  }
}
