import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info);
  }

  reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (!this.state.hasError) return this.props.children;

    const { title = 'Something went wrong', description } = this.props;
    const msg = description || this.state.error?.message || 'An unexpected error occurred.';

    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-destructive/30 bg-destructive/5 p-10 text-center">
        <AlertTriangle className="w-8 h-8 text-destructive" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="text-xs text-muted-foreground max-w-sm">{msg}</p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={this.reset}>
          <RefreshCw className="w-3.5 h-3.5" />
          Try again
        </Button>
      </div>
    );
  }
}
