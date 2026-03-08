import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-lg bg-gray-900 p-8">
          <p className="text-sm font-medium text-red-400">Something went wrong</p>
          <p className="max-w-md text-center text-xs text-gray-500">
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="rounded bg-gray-800 px-3 py-1.5 text-xs hover:bg-gray-700"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
