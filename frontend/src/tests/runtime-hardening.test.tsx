import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { safeFormatDate } from "../shared/lib/dates";
import {
  dateLabel,
  money,
  safeDateTime,
  safeTime,
  formatDate,
  formatDateTime,
} from "../shared/lib/format";
import { ErrorBoundary } from "../shared/components/ErrorBoundary";
import { ChartTooltip } from "../shared/components/ChartTooltip";
import CashCharts from "../modules/financeiro/components/CashCharts";
import {
  validateCashSummary,
  chartCents,
} from "../modules/financeiro/chart-contract";
import { DashboardPage } from "../modules/identity/pages/DashboardPage";
import { useAuth } from "../modules/identity/hooks/auth-store";
import type { Summary } from "../modules/financeiro/types";
const summary: Summary = {
  source: "demo",
  total_records: 1,
  income: "120.00",
  expense: "20.00",
  net: "100.00",
  pending_income: "0.00",
  pending_expense: "0.00",
  points: [
    {
      day: "2026-11-16",
      income: "120.00",
      expense: "20.00",
      pending_income: "0.00",
      pending_expense: "0.00",
    },
  ],
  expense_categories: [{ category: "Serviços", amount: "20.00" }],
};
const dateOptions = {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
} as const;
beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({
    matches: true,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  // Actual Recharts components, with a predictable layout supplied by jsdom.
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 800,
    height: 260,
    top: 0,
    left: 0,
    bottom: 260,
    right: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(private callback: ResizeObserverCallback) {}
      observe(target: Element) {
        this.callback(
          [
            {
              target,
              contentRect: target.getBoundingClientRect(),
            } as ResizeObserverEntry,
          ],
          this as unknown as ResizeObserver,
        );
      }
      disconnect() {}
      unobserve() {}
    },
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useAuth.getState().clear();
});
describe("date presentation is total for API and Recharts values", () => {
  it.each([undefined, null, "", "   "])("returns fallback for %s", (value) => {
    expect(safeFormatDate(value)).toBe("--");
    expect(() => dateLabel(value)).not.toThrow();
  });
  it.each([
    NaN,
    Infinity,
    new Date("invalid"),
    {},
    false,
    Symbol("bad"),
    "2026-W45",
    "Sem 1",
    "Jan/2026",
    "Nov/26",
    "2026-11",
    "not a date",
    "2026-02-30",
    "2026-13-01",
    "2026-11-16T25:00:00Z",
    "2026-11-16T12:00:00",
  ])("preserves labels/invalid strings: %s", (value) =>
    expect(safeFormatDate(value)).toBe(String(value)),
  );
  it("formats a calendar day without shifting it across timezones", () => {
    expect(
      safeFormatDate("2026-11-16", {
        ...dateOptions,
        timeZone: "America/Los_Angeles",
      }),
    ).toBe("16/11/2026");
    expect(safeFormatDate("2024-02-29", dateOptions)).toBe("29/02/2024");
    expect(safeFormatDate("2025-02-29", dateOptions)).toBe("2025-02-29");
  });
  it("handles Z, offsets and fractional API seconds", () => {
    for (const value of [
      "2026-11-16T12:00:00Z",
      "2026-11-16T09:00:00-03:00",
      "2026-11-16T12:00:00.123456+00:00",
    ])
      expect(safeFormatDate(value, dateOptions)).toBe("16/11/2026");
  });
  it("contains Intl errors and never renders null as a textual date", () => {
    expect(
      safeFormatDate("2026-11-16T12:00:00Z", { timeZone: "invalid" }),
    ).toBe("2026-11-16T12:00:00Z");
    expect(safeFormatDate("Sem\u00001")).toBe("Sem\u00001");
  });
});
it("reproduces the former tooltip crash and uses the safe replacement", () => {
  const previous = (value: unknown) =>
    new Intl.DateTimeFormat("pt-BR").format(
      new Date(`${String(value)}T12:00:00`),
    );
  expect(() => previous(undefined)).toThrow(RangeError);
  expect(() => previous("2026-11-16T12:00:00Z")).toThrow(RangeError);
  render(
    <ChartTooltip active={false} label={dateLabel(undefined)} payload={[]} />,
  );
  expect(screen.queryByText("Invalid Date")).toBeNull();
});
it("renders actual Recharts with missing/grouped date labels, including initial tooltip", async () => {
  const points = [
    null,
    undefined,
    "2026-W45",
    "Nov/26",
    "Sem 1",
    "2026-11-16",
    "2026-11-16T12:00:00Z",
  ].map((day) => ({ ...summary.points[0]!, day }));
  render(<CashCharts summary={{ ...summary, points } as unknown as Summary} />);
  await waitFor(() =>
    expect(document.querySelector("svg.recharts-surface")).not.toBeNull(),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  const checkbox = screen.getByLabelText("Previsto") as HTMLInputElement;
  await userEvent.click(checkbox);
  expect(checkbox.checked).toBe(true);
  expect(screen.getByText("Consultar dados do gráfico")).toBeTruthy();
});
it("rejects invalid finance values visibly instead of turning them into zero", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  expect(chartCents("1.2")).toBe(120n);
  expect(chartCents("-1.25")).toBe(-125n);
  expect(() =>
    validateCashSummary({
      ...summary,
      points: [{ ...summary.points[0], income: null }],
    }),
  ).toThrow();
  render(
    <>
      <p>Widget de estoque saudável</p>
      <CashCharts summary={{ ...summary, points: {} } as unknown as Summary} />
    </>,
  );
  expect(screen.getByRole("status").textContent).toContain(
    "Sem dados no período",
  );
  expect(screen.getByText("Widget de estoque saudável")).toBeTruthy();
  expect(money(null)).toBe("--");
  expect(money("NaN")).toBe("--");
});
it("isolates a widget failure, retries and resets on navigation", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  let broken = true;
  function Widget() {
    if (broken) throw new RangeError("Invalid time value");
    return <p>Gráfico recuperado</p>;
  }
  const tree = (key: string) => (
    <>
      <nav>Menu preservado</nav>
      <ErrorBoundary resetKeys={[key]}>
        <Widget />
      </ErrorBoundary>
    </>
  );
  const { rerender } = render(tree("finance"));
  expect(screen.getByText("Menu preservado")).toBeTruthy();
  expect(screen.getByText("Invalid time value")).toBeTruthy();
  broken = false;
  await userEvent.click(screen.getByText("Tentar novamente"));
  expect(screen.getByText("Gráfico recuperado")).toBeTruthy();
  broken = true;
  rerender(tree("finance"));
  expect(screen.getByRole("alert")).toBeTruthy();
  broken = false;
  rerender(tree("stock"));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
});
it("renders the restricted finance navigation icon for a non-finance user", async () => {
  const session = {
    token: "test",
    expiresAt: Date.now() + 900000,
    user: {
      user_id: "u",
      tenant_id: "t",
      display_name: "Vendedor",
      email: "v@test.com",
      permissions: ["identidade:dashboard:ler"],
    },
  };
  useAuth.getState().setSession(session);
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (url: string) =>
        new Response(
          JSON.stringify(
            url.includes("cockpit")
              ? { start: "2026-11-01", end: "2026-11-16", updated_at: null }
              : url.includes("/me")
                ? session.user
                : { tenant_name: "Empresa", activities: [], audit: [] },
          ),
        ),
    ),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <DashboardPage session={session} />
    </QueryClientProvider>,
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(document.querySelector(".lucide-lock-keyhole")).not.toBeNull();
});

it.each([
  null,
  undefined,
  { ...summary, points: [] },
  { ...summary, points: null },
  { ...summary, points: [null] },
  { ...summary, points: [{ ...summary.points[0], income: NaN }] },
  { ...summary, points: [{ ...summary.points[0], expense: "NaN" }] },
  { ...summary, points: [{ ...summary.points[0], pending_income: Infinity }] },
  { ...summary, income: null },
  { ...summary, expense_categories: null },
  { ...summary, expense_categories: [{ category: "Serviços", amount: null }] },
  { ...summary, points: [{ ...summary.points[0], income: null }] },
])("renders an empty state for missing API data (%j)", (value) => {
  render(<CashCharts summary={value} />);
  expect(screen.getByRole("status").textContent).toContain(
    "Sem dados no período",
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(document.querySelector("svg.recharts-surface")).toBeNull();
});

it("does not invoke Intl for non-ISO labels or invalid dates", () => {
  const intl = vi.spyOn(Intl, "DateTimeFormat");
  for (const value of [
    null,
    undefined,
    "",
    "2026-W45",
    "Sem 1",
    "Jan/2026",
    "2026-02-30",
    "2026-11-16T12:00:00+99:00",
  ]) {
    for (const format of [
      safeFormatDate,
      safeDateTime,
      safeTime,
      formatDate,
      formatDateTime,
    ])
      expect(() => format(value)).not.toThrow();
  }
  expect(intl).not.toHaveBeenCalled();
});
it("keeps epoch handling explicit for query update times", () => {
  const value = Date.parse("2026-11-16T12:00:00Z");
  expect(safeFormatDate(value)).toBe(String(value));
  expect(safeTime(value)).toBe("09:00");
});
