import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { ShieldAlert, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    // Update state so the next render will show the fallback UI.
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-[400px] flex flex-col items-center justify-center p-8 bg-red-50/30 border border-red-100 rounded-2xl m-4 text-center select-none animate-in fade-in">
          <div className="w-16 h-16 bg-red-100 text-red-600 rounded-full flex items-center justify-center mb-4 shadow-sm">
            <ShieldAlert size={32} />
          </div>
          <h2 className="text-lg font-black text-red-950 tracking-tight">Something went wrong</h2>
          <p className="text-sm text-red-800/70 mt-2 max-w-md">
            A component crashed in the application tree. This usually happens when unexpected data formats are received from the server.
          </p>
          <div className="mt-4 p-4 bg-red-950/5 rounded-lg border border-red-900/10 text-left max-w-2xl w-full overflow-x-auto">
            <pre className="text-[10px] md:text-xs font-mono text-red-900/80">
              {this.state.error?.toString()}
            </pre>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="mt-6 flex items-center gap-2 px-6 py-2.5 bg-white border border-red-200 hover:bg-red-50 text-red-700 rounded-xl font-bold text-sm shadow-sm transition-colors"
          >
            <RefreshCw size={16} />
            <span>Reload Application</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
