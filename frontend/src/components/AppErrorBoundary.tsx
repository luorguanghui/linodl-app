import {
  Component,
  Fragment,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { AlertTriangle } from "lucide-react";

interface AppErrorBoundaryProps {
  children: ReactNode;
  resetKey?: string;
}

interface AppErrorBoundaryState {
  error: Error | null;
  retryVersion: number;
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = {
    error: null,
    retryVersion: 0,
  };

  static getDerivedStateFromError(error: Error): Partial<AppErrorBoundaryState> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("页面渲染失败", error, info);
    }
  }

  componentDidUpdate(previousProps: AppErrorBoundaryProps) {
    if (
      this.state.error &&
      previousProps.resetKey !== this.props.resetKey
    ) {
      this.setState((state) => ({
        error: null,
        retryVersion: state.retryVersion + 1,
      }));
    }
  }

  private retry = () => {
    this.setState((state) => ({
      error: null,
      retryVersion: state.retryVersion + 1,
    }));
  };

  render() {
    if (this.state.error) {
      return (
        <section className="page-error" role="alert">
          <AlertTriangle
            className="page-error-icon"
            size={26}
            strokeWidth={1.8}
            aria-hidden="true"
          />
          <h1 className="page-error-title">此页面暂时无法显示</h1>
          <p className="page-error-detail">
            页面内容遇到渲染问题。全局任务仍在运行，可以重新加载当前页面。
          </p>
          <button
            className="page-error-button"
            type="button"
            onClick={this.retry}
          >
            重新加载页面
          </button>
        </section>
      );
    }

    return (
      <Fragment key={this.state.retryVersion}>{this.props.children}</Fragment>
    );
  }
}
