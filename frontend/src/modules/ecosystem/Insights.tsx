import { ErrorBoundary } from "../../shared/components/ErrorBoundary";
import { lazy, Suspense } from "react";
const Content = lazy(() => import("./InsightsContent"));
export function Insights(props: {
  source: string;
  start: string;
  end: string;
  salesOnly?: boolean;
}) {
  return (
    <ErrorBoundary
      resetKeys={[props.source, props.start, props.end, props.salesOnly]}
    >
      <Suspense
        fallback={
          <div className="chart-skeleton" aria-label="Carregando análise" />
        }
      >
        <Content {...props} />
      </Suspense>
    </ErrorBoundary>
  );
}
