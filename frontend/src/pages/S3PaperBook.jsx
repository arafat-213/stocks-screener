import { useState, useEffect, Suspense, lazy } from 'react';
import { getOr, isEmpty, map } from 'lodash/fp';
import {
  Lock,
  Wallet,
  TrendingUp,
  Layers,
  CalendarClock,
  AlertCircle,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  Repeat,
  ChevronDown,
  ChevronRight,
  PieChart,
  TrendingDown,
  Receipt,
} from 'lucide-react';
import {
  getPaperV2Book,
  getPaperV2Positions,
  getPaperV2Nav,
  getPaperV2Parity,
  getPaperV2Rebalances,
} from '../api/client';
import { useTheme } from '../hooks/useTheme';
import { formatDisplayDate } from '../utils/dateUtils';

// bundle-dynamic-imports: lazy-load the heavy chart lib (copied from Backtest.jsx)
const LineChart = lazy(() =>
  import('recharts').then((m) => ({ default: m.LineChart }))
);
const Line = lazy(() => import('recharts').then((m) => ({ default: m.Line })));
const Area = lazy(() => import('recharts').then((m) => ({ default: m.Area })));
const AreaChart = lazy(() =>
  import('recharts').then((m) => ({ default: m.AreaChart }))
);
const XAxis = lazy(() =>
  import('recharts').then((m) => ({ default: m.XAxis }))
);
const YAxis = lazy(() =>
  import('recharts').then((m) => ({ default: m.YAxis }))
);
const CartesianGrid = lazy(() =>
  import('recharts').then((m) => ({ default: m.CartesianGrid }))
);
const Tooltip = lazy(() =>
  import('recharts').then((m) => ({ default: m.Tooltip }))
);
const ResponsiveContainer = lazy(() =>
  import('recharts').then((m) => ({ default: m.ResponsiveContainer }))
);
const Legend = lazy(() =>
  import('recharts').then((m) => ({ default: m.Legend }))
);
const ReferenceLine = lazy(() =>
  import('recharts').then((m) => ({ default: m.ReferenceLine }))
);

// Business-day (Mon–Fri) gap between two YYYY-MM-DD strings. A holiday-blind
// proxy for "trading days" — we have no NSE calendar on the client, so this can
// over-count by the number of intervening holidays (acceptable for a staleness
// hint; see specs/v3/11 V11.6 #4).
const businessDaysBetween = (fromStr, toStr) => {
  if (!fromStr || !toStr) return 0;
  const from = new Date(`${fromStr}T00:00:00Z`);
  const to = new Date(`${toStr}T00:00:00Z`);
  let count = 0;
  const cur = new Date(from);
  while (cur < to) {
    cur.setUTCDate(cur.getUTCDate() + 1);
    const dow = cur.getUTCDay();
    if (dow !== 0 && dow !== 6) count += 1;
  }
  return count;
};

// Name-concentration of the held sleeve — the §6.2 gate this whole research arc
// kept dying on (skew-recheck-cracks-index-wall). Weights are taken WITHIN the
// invested book (market_value / Σ market_value), so the figures describe how lumpy
// the equity is independent of how much cash is parked. HHI = Σ wᵢ² ("how skewed
// is the basket"); effective-N = 1/HHI ("how many equal-weight names this behaves
// like"). Returns null when fully in cash (nothing to concentrate).
const concentrationStats = (positions) => {
  const mvs = positions
    .map((p) => getOr(0, 'market_value')(p))
    .filter((v) => v > 0);
  const total = mvs.reduce((a, b) => a + b, 0);
  if (!total) return null;
  const weights = [...mvs].sort((a, b) => b - a).map((v) => v / total);
  const hhi = weights.reduce((a, w) => a + w * w, 0);
  return {
    n: positions.length,
    top1: weights[0] * 100,
    top5: weights.slice(0, 5).reduce((a, w) => a + w, 0) * 100,
    effN: hhi > 0 ? 1 / hhi : 0,
  };
};

// Running-peak (underwater) drawdown series in %, ≤ 0, for both the book NAV and
// the rebased Mom30 overlay. A drawdown is peak-to-trough decline — "how far below
// its own high-water mark each line currently sits". Index drawdown is computed
// only over points that carry an index level (gaps leave a null the chart skips).
const drawdownSeries = (points) => {
  let peakEq = -Infinity;
  let peakIx = -Infinity;
  return points.map((p) => {
    if (p.equity != null && p.equity > peakEq) peakEq = p.equity;
    const bookDd = peakEq > 0 ? (p.equity / peakEq - 1) * 100 : 0;
    let indexDd = null;
    if (p.index_rebased != null) {
      if (p.index_rebased > peakIx) peakIx = p.index_rebased;
      indexDd = peakIx > 0 ? (p.index_rebased / peakIx - 1) * 100 : 0;
    }
    return { date: p.date, bookDd, indexDd };
  });
};

const minOr0 = (vals) => (vals.length ? Math.min(...vals) : 0);

// Cumulative excess return (book − index) in %. Anchored to the first point that has
// both an equity and an index value so the two series start from the same base. Gaps
// in the index (points missing index_rebased) are dropped — they leave no trail.
const excessReturnSeries = (points) => {
  const first = points.find((p) => p.equity != null && p.index_rebased != null);
  if (!first) return [];
  const baseEq = first.equity;
  const baseIx = first.index_rebased;
  return points
    .filter((p) => p.equity != null && p.index_rebased != null)
    .map((p) => ({
      date: p.date,
      excess: (p.equity / baseEq - p.index_rebased / baseIx) * 100,
    }));
};

// Cumulative trading-cost (the literal point of a paper probation: cost realism)
// plus cumulative turnover. Cost = Σ total_cost_rupees (fees + slippage). Turnover
// = Σ qty·fill_price over filled fills — the traded notional, expressed as a
// multiple of starting capital ("the book churned N× its own size"); turnover is
// the documented driver of this strategy's cost story. Events arrive newest-first,
// so we re-sort ascending to accumulate.
const costStats = (events, startingCapital) => {
  const asc = [...events].sort((a, b) =>
    a.decision_date < b.decision_date ? -1 : 1
  );
  let cumCost = 0;
  let cumTurnover = 0;
  const series = asc.map((ev) => {
    cumCost += getOr(0, 'total_cost_rupees')(ev);
    cumTurnover += getOr(
      [],
      'fills'
    )(ev).reduce((s, f) => {
      const qty = getOr(0, 'qty')(f);
      return s + (f.fill_price != null ? qty * f.fill_price : 0);
    }, 0);
    return { date: ev.decision_date, cumCost };
  });
  return {
    totalCost: cumCost,
    costPct: startingCapital ? (cumCost / startingCapital) * 100 : 0,
    turnoverX: startingCapital ? cumTurnover / startingCapital : 0,
    series,
  };
};

// Read-only view of the frozen S3 forward paper book (specs/v3/11 §1).
// No add / close controls by design: the probation is a frozen experiment.
const S3PaperBook = () => {
  const { isDark } = useTheme();
  const [book, setBook] = useState(null);
  const [positions, setPositions] = useState([]);
  const [nav, setNav] = useState(null);
  const [parity, setParity] = useState(null);
  const [rebalances, setRebalances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notArmed, setNotArmed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        // Each new endpoint .catch → null/[] so one failing call never blanks the
        // page (matches the 404-tolerant pattern already used for getPaperV2Book).
        const [bookData, posData, navData, parityData, rebalData] =
          await Promise.all([
            getPaperV2Book().catch((err) => {
              if (err?.response?.status === 404) {
                setNotArmed(true);
                return null;
              }
              throw err;
            }),
            getPaperV2Positions().catch(() => []),
            getPaperV2Nav().catch(() => null),
            getPaperV2Parity().catch(() => null),
            getPaperV2Rebalances().catch(() => []),
          ]);
        setBook(bookData);
        setPositions(posData || []);
        setNav(navData);
        setParity(parityData);
        setRebalances(rebalData || []);
      } catch (error) {
        console.error('Error loading S3 paper book:', error);
      } finally {
        setLoading(false);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  if (loading) {
    return (
      <div className='flex items-center justify-center min-h-[400px]'>
        <div className='flex flex-col items-center gap-4'>
          <div className='w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin'></div>
          <p className='text-text-muted font-bold uppercase tracking-widest text-xs'>
            Loading S3 Book...
          </p>
        </div>
      </div>
    );
  }

  if (notArmed || !book) {
    return (
      <div className='w-full flex flex-col gap-8 pb-24 animate-fade-in'>
        <PageHeader parity={parity} />
        <div className='flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center'>
          <AlertCircle size={48} className='text-text-muted mb-4 opacity-20' />
          <h3 className='text-lg font-bold text-text mb-2'>
            Probation Not Armed
          </h3>
          <p className='text-text-muted max-w-md'>
            There is no active S3 probation book yet. Once the{' '}
            <span className='font-mono'>11</span> forward run is armed, the book
            NAV and holdings will appear here.
          </p>
        </div>
      </div>
    );
  }

  const navValue = getOr(0, 'nav')(book);
  const ret = getOr(0, 'total_return_pct')(book);

  return (
    <div className='w-full flex flex-col gap-8 pb-24 animate-fade-in'>
      <PageHeader parity={parity} />

      <StalenessBanner book={book} />

      {/* Book header cards */}
      <div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6'>
        <StatCard
          label='Net Asset Value'
          value={`₹${navValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          subValue={`from ₹${getOr(0, 'starting_capital')(book).toLocaleString(undefined, { maximumFractionDigits: 0 })} start`}
          icon={<TrendingUp className='text-primary' size={20} />}
          trend={ret >= 0 ? 'up' : 'down'}
          trendLabel={`${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`}
        />
        <StatCard
          label='Cash'
          value={`₹${getOr(0, 'cash')(book).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          subValue={`₹${getOr(0, 'holdings_value')(book).toLocaleString(undefined, { maximumFractionDigits: 0 })} in holdings`}
          icon={<Wallet className='text-blue-500' size={20} />}
        />
        <StatCard
          label='Holdings'
          value={`${getOr(0, 'n_positions')(book)}`}
          subValue='open positions'
          icon={<Layers className='text-bullish' size={20} />}
        />
        <StatCard
          label='Replay Clock'
          value={
            book.last_processed_date
              ? formatDisplayDate(book.last_processed_date)
              : '—'
          }
          subValue={
            book.go_live_date
              ? `go-live ${formatDisplayDate(book.go_live_date)}`
              : 'not armed'
          }
          icon={<CalendarClock className='text-amber-500' size={20} />}
        />
      </div>

      {/* Probation progress */}
      <ProbationProgress book={book} />

      {/* NAV curve + benchmark overlay + exposure band */}
      <NavCurve nav={nav} isDark={isDark} />

      {/* Underwater (drawdown) curve — book vs Mom30 */}
      <DrawdownCurve nav={nav} isDark={isDark} />

      {/* Name-concentration panel (§6.2 gate) */}
      <ConcentrationPanel positions={positions} />

      {/* Holdings */}
      <HoldingsTable positions={positions} />

      {/* Cumulative cost-drag + turnover */}
      <CostDragPanel rebalances={rebalances} book={book} isDark={isDark} />

      {/* Rebalance log */}
      <RebalanceLog events={rebalances} />
    </div>
  );
};

// --- Sub-components ---

const PageHeader = ({ parity }) => (
  <header className='flex flex-col md:flex-row justify-between items-start gap-4'>
    <div className='flex flex-col'>
      <h1 className='text-3xl font-black tracking-tight text-text'>
        S3 Paper Book
      </h1>
      <p className='text-text-muted'>
        Frozen forward probation of the S3 momentum strategy
      </p>
    </div>
    <div className='flex items-center gap-2 flex-wrap justify-end'>
      <FidelityBadge parity={parity} />
      <div className='flex items-center gap-2 px-4 py-2 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-500 h-[42px]'>
        <Lock size={16} />
        <span className='text-xs font-black uppercase tracking-widest'>
          Read-only · Frozen
        </span>
      </div>
    </div>
  </header>
);

// Shadow-parity fidelity chip (specs/v3/11 V11.6 #1). Green PASS / red BREAK,
// fed by parity.latest. A BREAK anywhere in history surfaces a persistent
// "clock reset" note (the 6-month window restarts on a break, 11 §7.1).
const FidelityBadge = ({ parity }) => {
  const latest = getOr(null, 'latest')(parity);
  const history = getOr([], 'history')(parity);
  const everBroke = history.some((c) => !c.passed);

  if (!latest) {
    return (
      <div className='flex items-center gap-2 px-4 py-2 bg-bg-elevated border border-border rounded-xl text-text-muted h-[42px]'>
        <ShieldCheck size={16} />
        <span className='text-xs font-black uppercase tracking-widest'>
          No parity check yet
        </span>
      </div>
    );
  }

  return (
    <div className='flex items-center gap-2'>
      {everBroke && (
        <div className='flex items-center gap-1.5 px-3 py-2 bg-bearish/10 border border-bearish/30 rounded-xl text-bearish h-[42px]'>
          <AlertTriangle size={14} />
          <span className='text-[10px] font-black uppercase tracking-widest'>
            Clock Reset
          </span>
        </div>
      )}
      {latest.passed ? (
        <div className='flex items-center gap-2 px-4 py-2 bg-bullish/10 border border-bullish/30 rounded-xl text-bullish h-[42px]'>
          <ShieldCheck size={16} />
          <span className='text-xs font-black uppercase tracking-widest'>
            Pass · {latest.max_dev_bps.toFixed(1)} bps
          </span>
        </div>
      ) : (
        <div className='flex items-center gap-2 px-4 py-2 bg-bearish/10 border border-bearish/30 rounded-xl text-bearish h-[42px]'>
          <ShieldAlert size={16} />
          <span className='text-xs font-black uppercase tracking-widest'>
            Break · {formatDisplayDate(latest.as_of)}
          </span>
        </div>
      )}
    </div>
  );
};

// Staleness warning (specs/v3/11 V11.6 #4). The worker/beat have been stopped
// before — if the replay clock lags the latest expected trading day by >2
// trading days, surface a visible banner. Threshold is LOCKED at 2.
const StalenessBanner = ({ book }) => {
  const last = book?.last_processed_date;
  if (!last) return null;
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
  const lag = businessDaysBetween(last, today);
  if (lag <= 2) return null;

  return (
    <div className='flex items-center gap-3 p-4 bg-amber-500/10 border-2 border-amber-500/30 rounded-2xl text-amber-600 dark:text-amber-400 shadow-sm'>
      <AlertTriangle size={20} className='shrink-0 text-amber-500' />
      <div className='text-sm font-bold'>
        <span className='uppercase tracking-widest text-[10px] block mb-0.5 font-black'>
          Replay Stale
        </span>
        Last processed {formatDisplayDate(last)} — roughly {lag} trading days
        behind. Check the daily post-close worker &amp; beat are running.
      </div>
    </div>
  );
};

// Probation progress bar (specs/v3/11 V11.6 #4). Denominator is LOCKED to
// CALENDAR months: go_live_date → go_live_date + 6 months (a trading-day count
// drifts on holidays; the 11 prereg frames probation as "6 forward months").
const ProbationProgress = ({ book }) => {
  const goLive = book?.go_live_date;
  if (!goLive) return null;

  const start = new Date(`${goLive}T00:00:00Z`);
  const end = new Date(start);
  end.setUTCMonth(end.getUTCMonth() + 6);
  const now = new Date();
  const total = end - start;
  const elapsed = Math.max(0, Math.min(total, now - start));
  const pct = total > 0 ? (elapsed / total) * 100 : 0;
  const done = now >= end;

  const endStr = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(end);

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-3'>
      <div className='flex justify-between items-center'>
        <span className='text-[10px] font-black uppercase tracking-widest text-text-muted'>
          6-Month Forward Probation
        </span>
        <span className='text-xs font-black text-text'>
          {done ? 'Window complete' : `${pct.toFixed(0)}% elapsed`}
        </span>
      </div>
      <div className='h-2 bg-border rounded-full overflow-hidden'>
        <div
          className={`h-full rounded-full transition-all duration-1000 ease-out ${done ? 'bg-bullish' : 'bg-primary'}`}
          style={{ width: `${pct}%` }}
        ></div>
      </div>
      <div className='flex justify-between text-[10px] font-bold text-text-muted uppercase tracking-wider'>
        <span>Go-live {formatDisplayDate(goLive)}</span>
        <span>Target {formatDisplayDate(endStr)}</span>
      </div>
    </div>
  );
};

// Custom NAV-curve tooltip: date, book NAV, rebased index, and the gap (book −
// index) in ₹ and %.
const NavTooltip = ({ active, payload, label, isDark }) => {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0]?.payload || {};
  const equity = point.equity;
  const index = point.index_rebased;
  const gap = index != null ? equity - index : null;
  const gapPct = index ? (gap / index) * 100 : null;
  return (
    <div
      className='rounded-xl border-2 px-3 py-2 font-mono text-xs shadow-lg'
      style={{
        backgroundColor: isDark ? '#0F172A' : '#FFFFFF',
        borderColor: isDark ? '#1E293B' : '#E2E8F0',
      }}
    >
      <div className='font-black mb-1 text-text'>
        {formatDisplayDate(label)}
      </div>
      <div className='text-primary font-bold'>
        NAV ₹{equity?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </div>
      {index != null && (
        <div className='text-text-muted'>
          Index ₹{index.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </div>
      )}
      {gap != null && (
        <div className={gap >= 0 ? 'text-bullish' : 'text-bearish'}>
          Gap {gap >= 0 ? '+' : ''}₹
          {gap.toLocaleString(undefined, { maximumFractionDigits: 0 })} (
          {gapPct >= 0 ? '+' : ''}
          {gapPct.toFixed(2)}%)
        </div>
      )}
    </div>
  );
};

// Equity/NAV curve (specs/v3/11 V11.6 #2): full since-inception curve, a go-live
// divider (warm-start replay ↔ live paper), the rebased Mom30 benchmark overlay,
// and a subordinate exposure strip (risk-on/off proxy).
const NavCurve = ({ nav, isDark }) => {
  const points = getOr([], 'points')(nav);
  const goLive = getOr(null, 'go_live_date')(nav);

  const axisColor = '#64748B';
  const gridColor = isDark ? '#1E293B' : '#E2E8F0';

  if (isEmpty(points)) {
    return (
      <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm'>
        <h3 className='text-lg font-black flex items-center gap-3 mb-6 text-text uppercase tracking-tight'>
          <TrendingUp size={20} className='text-primary' /> NAV Curve
        </h3>
        <div className='flex flex-col items-center justify-center py-16 text-center'>
          <TrendingUp size={40} className='text-text-muted mb-3 opacity-20' />
          <p className='text-text-muted max-w-xs'>
            No NAV history yet. The curve populates after the first daily replay
            run persists its snapshots.
          </p>
        </div>
      </div>
    );
  }

  // Anchor the divider to the first counted-forward point so it lands exactly on
  // a data x-value (go_live itself may be a weekend/holiday with no snapshot).
  const firstForward = points.find((p) => p.is_forward);
  const dividerX = firstForward ? firstForward.date : goLive;

  const excessPoints = excessReturnSeries(points);
  const latestExcess = excessPoints.length
    ? excessPoints[excessPoints.length - 1].excess
    : 0;

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm'>
      <div className='flex flex-wrap justify-between items-center gap-2 mb-6'>
        <h3 className='text-lg font-black flex items-center gap-3 text-text uppercase tracking-tight'>
          <TrendingUp size={20} className='text-primary' /> NAV Curve
        </h3>
        <span className='text-[10px] font-bold text-text-muted uppercase tracking-widest'>
          Warm-start replay · Live paper (after divider)
        </span>
      </div>

      <div className='w-full h-[360px]'>
        <Suspense
          fallback={
            <div className='w-full h-full flex items-center justify-center bg-bg-elevated rounded-xl'>
              <Loader2 className='animate-spin text-primary' size={32} />
            </div>
          }
        >
          <ResponsiveContainer>
            <LineChart
              data={points}
              margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray='3 3'
                stroke={gridColor}
                vertical={false}
              />
              <XAxis
                dataKey='date'
                stroke={axisColor}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dy={10}
                minTickGap={40}
                tickFormatter={(str) => formatDisplayDate(str)}
              />
              <YAxis
                stroke={axisColor}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dx={-10}
                domain={['auto', 'auto']}
                tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<NavTooltip isDark={isDark} />} />
              <Legend
                verticalAlign='top'
                align='right'
                iconType='circle'
                wrapperStyle={{
                  paddingBottom: '16px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                }}
              />
              {dividerX && (
                <ReferenceLine
                  x={dividerX}
                  stroke='#F59E0B'
                  strokeDasharray='4 4'
                  strokeWidth={2}
                  label={{
                    value: 'GO-LIVE',
                    position: 'insideTopRight',
                    fill: '#F59E0B',
                    fontSize: 10,
                    fontWeight: 900,
                  }}
                />
              )}
              <Line
                name='Book NAV'
                type='monotone'
                dataKey='equity'
                stroke='#3B82F6'
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, strokeWidth: 0, fill: '#3B82F6' }}
              />
              <Line
                name='Mom30 Index (rebased)'
                type='monotone'
                dataKey='index_rebased'
                stroke='#94A3B8'
                strokeWidth={2}
                strokeDasharray='6 4'
                dot={false}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </Suspense>
      </div>

      {/* Excess-return strip — book cumulative return minus Mom30 cumulative return.
          Answers "beating the index or buying it with extra steps?" at a glance. */}
      {excessPoints.length > 0 && (
        <div className='mt-4'>
          <div className='flex justify-between items-center mb-1 px-1'>
            <span className='text-[9px] font-black uppercase tracking-widest text-text-muted'>
              Cumulative Excess Return (Book − Mom30)
            </span>
            <span
              className={`text-[9px] font-black ${latestExcess >= 0 ? 'text-bullish' : 'text-bearish'}`}
            >
              {latestExcess >= 0 ? '+' : ''}
              {latestExcess.toFixed(2)}%
            </span>
          </div>
          <div className='w-full h-[72px]'>
            <Suspense fallback={<div className='w-full h-full' />}>
              <ResponsiveContainer>
                <LineChart
                  data={excessPoints}
                  margin={{ top: 4, right: 8, left: 8, bottom: 0 }}
                >
                  <XAxis dataKey='date' hide />
                  <YAxis hide domain={['auto', 'auto']} />
                  <ReferenceLine
                    y={0}
                    stroke={axisColor}
                    strokeWidth={1}
                    strokeDasharray='3 3'
                  />
                  <Line
                    type='monotone'
                    dataKey='excess'
                    stroke={latestExcess >= 0 ? '#10B981' : '#EF4444'}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Suspense>
          </div>
        </div>
      )}

      {/* Exposure band — risk-on (~1) / risk-off (in cash, 0). Subordinate to the
          NAV curve; surfaces regime transitions without persisting regime state. */}
      <div className='mt-2'>
        <div className='flex justify-between items-center mb-1 px-1'>
          <span className='text-[9px] font-black uppercase tracking-widest text-text-muted'>
            Exposure (risk-on / off)
          </span>
        </div>
        <div className='w-full h-[64px]'>
          <Suspense fallback={<div className='w-full h-full' />}>
            <ResponsiveContainer>
              <AreaChart
                data={points}
                margin={{ top: 0, right: 8, left: 8, bottom: 0 }}
              >
                <XAxis dataKey='date' hide />
                <YAxis domain={[0, 1]} hide />
                <Area
                  type='stepAfter'
                  dataKey='exposure'
                  stroke='#10B981'
                  fill='#10B981'
                  fillOpacity={0.18}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </Suspense>
        </div>
      </div>
    </div>
  );
};

// Name-concentration panel (specs/v3/11; §6.2). The concentration gate is the one
// this strategy repeatedly failed, so the live book surfaces it directly. Hidden
// when the book is fully in cash (the holdings table explains that state).
const ConcentrationPanel = ({ positions }) => {
  const stats = concentrationStats(positions);
  if (!stats) return null;

  const cells = [
    { label: 'Holdings', value: `${stats.n}`, sub: 'open names' },
    {
      label: 'Largest',
      value: `${stats.top1.toFixed(1)}%`,
      sub: 'of holdings',
    },
    {
      label: 'Top 5',
      value: `${stats.top5.toFixed(1)}%`,
      sub: 'of holdings',
    },
    {
      label: 'Effective N',
      value: stats.effN.toFixed(1),
      sub: 'equal-weight equiv.',
    },
  ];

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm'>
      <h3 className='text-lg font-black flex items-center gap-3 mb-1 text-text uppercase tracking-tight'>
        <PieChart size={20} className='text-primary' /> Concentration
      </h3>
      <p className='text-[11px] font-bold text-text-muted mb-6'>
        How lumpy the held sleeve is — the §6.2 gate. Weights are within
        holdings (excl. cash); effective-N is 1/HHI.
      </p>
      <div className='grid grid-cols-2 xl:grid-cols-4 gap-4'>
        {map((c) => (
          <div
            key={c.label}
            className='bg-bg-elevated border border-border rounded-xl p-4 flex flex-col gap-1'
          >
            <span className='text-[10px] font-black uppercase tracking-widest text-text-muted'>
              {c.label}
            </span>
            <span className='text-2xl font-black text-text tracking-tight'>
              {c.value}
            </span>
            <span className='text-[10px] font-bold text-text-muted uppercase tracking-wider'>
              {c.sub}
            </span>
          </div>
        ))(cells)}
      </div>
    </div>
  );
};

// Underwater / drawdown curve (specs/v3/11 viz). Plots peak-to-trough decline for
// the book NAV and the rebased Mom30 overlay on one axis, with the worst level
// each reached as a headline chip. No deploy-bar line is drawn: the maxDD bar's
// exact denominator (08 §2b) is a research artefact and hard-coding it here would
// risk misrepresenting it.
const DrawdownCurve = ({ nav, isDark }) => {
  const points = getOr([], 'points')(nav);
  if (isEmpty(points)) return null;

  const series = drawdownSeries(points);
  const bookMax = minOr0(series.map((d) => d.bookDd));
  const indexMax = minOr0(
    series.map((d) => d.indexDd).filter((v) => v != null)
  );
  const cur = series[series.length - 1] || {};

  const axisColor = '#64748B';
  const gridColor = isDark ? '#1E293B' : '#E2E8F0';

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm'>
      <div className='flex flex-wrap justify-between items-center gap-3 mb-6'>
        <h3 className='text-lg font-black flex items-center gap-3 text-text uppercase tracking-tight'>
          <TrendingDown size={20} className='text-bearish' /> Drawdown
        </h3>
        <div className='flex items-center gap-2 flex-wrap'>
          <DdChip label='Book max' value={bookMax} tone='book' />
          <DdChip label='Index max' value={indexMax} tone='index' />
          <DdChip label='Book now' value={cur.bookDd ?? 0} tone='book' />
        </div>
      </div>
      <div className='w-full h-[260px]'>
        <Suspense
          fallback={
            <div className='w-full h-full flex items-center justify-center bg-bg-elevated rounded-xl'>
              <Loader2 className='animate-spin text-primary' size={32} />
            </div>
          }
        >
          <ResponsiveContainer>
            <AreaChart
              data={series}
              margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray='3 3'
                stroke={gridColor}
                vertical={false}
              />
              <XAxis
                dataKey='date'
                stroke={axisColor}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dy={10}
                minTickGap={40}
                tickFormatter={(str) => formatDisplayDate(str)}
              />
              <YAxis
                stroke={axisColor}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dx={-10}
                domain={['auto', 0]}
                tickFormatter={(val) => `${val.toFixed(0)}%`}
              />
              <Tooltip content={<DrawdownTooltip isDark={isDark} />} />
              <Legend
                verticalAlign='top'
                align='right'
                iconType='circle'
                wrapperStyle={{
                  paddingBottom: '16px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                }}
              />
              <ReferenceLine y={0} stroke={axisColor} strokeWidth={1} />
              <Area
                name='Book'
                type='monotone'
                dataKey='bookDd'
                stroke='#EF4444'
                fill='#EF4444'
                fillOpacity={0.16}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Area
                name='Mom30 Index'
                type='monotone'
                dataKey='indexDd'
                stroke='#94A3B8'
                fill='#94A3B8'
                fillOpacity={0.08}
                strokeWidth={1.5}
                strokeDasharray='6 4'
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </Suspense>
      </div>
    </div>
  );
};

const DdChip = ({ label, value, tone }) => (
  <div className='flex items-center gap-1.5 px-3 py-1.5 bg-bg-elevated border border-border rounded-lg'>
    <span className='text-[9px] font-black uppercase tracking-widest text-text-muted'>
      {label}
    </span>
    <span
      className={`text-xs font-black ${tone === 'index' ? 'text-text-muted' : 'text-bearish'}`}
    >
      {value.toFixed(1)}%
    </span>
  </div>
);

const DrawdownTooltip = ({ active, payload, label, isDark }) => {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0]?.payload || {};
  return (
    <div
      className='rounded-xl border-2 px-3 py-2 font-mono text-xs shadow-lg'
      style={{
        backgroundColor: isDark ? '#0F172A' : '#FFFFFF',
        borderColor: isDark ? '#1E293B' : '#E2E8F0',
      }}
    >
      <div className='font-black mb-1 text-text'>
        {formatDisplayDate(label)}
      </div>
      <div className='text-bearish font-bold'>
        Book {point.bookDd?.toFixed(2)}%
      </div>
      {point.indexDd != null && (
        <div className='text-text-muted'>Index {point.indexDd.toFixed(2)}%</div>
      )}
    </div>
  );
};

// Cumulative cost-drag panel (specs/v3/11; cost realism is the point of probation).
// Headline = trading costs eaten so far as a % of starting capital, plus cumulative
// turnover (×capital). The mini chart traces cost accrual over the rebalance dates.
// Hidden until the first rebalance queues fills.
const CostDragPanel = ({ rebalances, book, isDark }) => {
  if (isEmpty(rebalances)) return null;
  const startingCapital = getOr(0, 'starting_capital')(book);
  const stats = costStats(rebalances, startingCapital);

  const axisColor = '#64748B';
  const gridColor = isDark ? '#1E293B' : '#E2E8F0';

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm'>
      <div className='flex flex-wrap justify-between items-center gap-3 mb-6'>
        <h3 className='text-lg font-black flex items-center gap-3 text-text uppercase tracking-tight'>
          <Receipt size={20} className='text-amber-500' /> Cost Drag
        </h3>
        <div className='flex items-center gap-2 flex-wrap'>
          <DdChip label='Cost' value={stats.costPct} tone='index' />
          <div className='flex items-center gap-1.5 px-3 py-1.5 bg-bg-elevated border border-border rounded-lg'>
            <span className='text-[9px] font-black uppercase tracking-widest text-text-muted'>
              Turnover
            </span>
            <span className='text-xs font-black text-amber-500'>
              {stats.turnoverX.toFixed(2)}×
            </span>
          </div>
          <div className='flex items-center gap-1.5 px-3 py-1.5 bg-bg-elevated border border-border rounded-lg'>
            <span className='text-[9px] font-black uppercase tracking-widest text-text-muted'>
              ₹ Cost
            </span>
            <span className='text-xs font-black text-text'>
              ₹
              {stats.totalCost.toLocaleString(undefined, {
                maximumFractionDigits: 0,
              })}
            </span>
          </div>
        </div>
      </div>
      <p className='text-[11px] font-bold text-text-muted mb-4'>
        Trading costs (fees + slippage) consumed so far ={' '}
        <span className='text-text'>{stats.costPct.toFixed(2)}%</span> of the ₹
        {startingCapital.toLocaleString(undefined, {
          maximumFractionDigits: 0,
        })}{' '}
        start. Turnover = traded notional ÷ capital.
      </p>
      <div className='w-full h-[200px]'>
        <Suspense
          fallback={
            <div className='w-full h-full flex items-center justify-center bg-bg-elevated rounded-xl'>
              <Loader2 className='animate-spin text-primary' size={32} />
            </div>
          }
        >
          <ResponsiveContainer>
            <AreaChart
              data={stats.series}
              margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray='3 3'
                stroke={gridColor}
                vertical={false}
              />
              <XAxis
                dataKey='date'
                stroke={axisColor}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dy={10}
                minTickGap={40}
                tickFormatter={(str) => formatDisplayDate(str)}
              />
              <YAxis
                stroke={axisColor}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dx={-10}
                tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CostTooltip isDark={isDark} />} />
              <Area
                name='Cumulative cost'
                type='monotone'
                dataKey='cumCost'
                stroke='#F59E0B'
                fill='#F59E0B'
                fillOpacity={0.16}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </Suspense>
      </div>
    </div>
  );
};

const CostTooltip = ({ active, payload, label, isDark }) => {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0]?.payload || {};
  return (
    <div
      className='rounded-xl border-2 px-3 py-2 font-mono text-xs shadow-lg'
      style={{
        backgroundColor: isDark ? '#0F172A' : '#FFFFFF',
        borderColor: isDark ? '#1E293B' : '#E2E8F0',
      }}
    >
      <div className='font-black mb-1 text-text'>
        {formatDisplayDate(label)}
      </div>
      <div className='text-amber-500 font-bold'>
        Cum. cost ₹
        {point.cumCost?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </div>
    </div>
  );
};

const StatCard = ({ label, value, subValue, icon, trend, trendLabel }) => (
  <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-4 relative overflow-hidden group'>
    <div className='flex justify-between items-start'>
      <div className='flex flex-col gap-1'>
        <span className='text-[10px] font-black uppercase tracking-widest text-text-muted'>
          {label}
        </span>
        <span className='text-2xl font-black text-text tracking-tight'>
          {value}
        </span>
      </div>
      <div className='p-2 bg-bg-elevated rounded-xl border border-border shadow-sm group-hover:scale-110 transition-transform'>
        {icon}
      </div>
    </div>
    <div className='flex items-center gap-2'>
      {trend && (
        <div
          className={`flex items-center gap-0.5 text-xs font-black ${trend === 'up' ? 'text-bullish' : 'text-bearish'}`}
        >
          {trend === 'up' ? (
            <ArrowUpRight size={14} />
          ) : (
            <ArrowDownRight size={14} />
          )}
          {trendLabel}
        </div>
      )}
      <span className='text-xs font-bold text-text-muted'>{subValue}</span>
    </div>
  </div>
);

const HoldingsTable = ({ positions }) => {
  if (isEmpty(positions)) {
    return (
      <div className='flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center'>
        <Layers size={48} className='text-text-muted mb-4 opacity-20' />
        <h3 className='text-lg font-bold text-text mb-2'>Fully in Cash</h3>
        <p className='text-text-muted max-w-xs'>
          The book holds no positions right now (a risk-off edge holds the book
          in cash). Holdings will appear after the next rebalance into risk-on.
        </p>
      </div>
    );
  }

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm'>
      <div className='overflow-x-auto'>
        <table className='w-full border-collapse'>
          <thead>
            <tr className='bg-bg-elevated border-b border-border text-[10px] uppercase tracking-widest text-text-muted font-black'>
              <th className='text-left p-4'>Symbol</th>
              <th className='text-right p-4'>Shares</th>
              <th className='text-right p-4'>Avg Cost</th>
              <th className='text-right p-4'>Last Price</th>
              <th className='text-right p-4'>Market Value</th>
              <th className='text-right p-4'>Unrealized %</th>
              <th className='text-right p-4'>Weight %</th>
              <th className='text-right p-4'>Score</th>
              <th className='text-right p-4'>Wt Drift</th>
              <th className='text-left p-4'>Entry Date</th>
            </tr>
          </thead>
          <tbody className='text-sm'>
            {map((pos) => {
              const pnlPct = getOr(0, 'unrealized_pct')(pos);
              const pnlColor = pnlPct >= 0 ? 'text-bullish' : 'text-bearish';
              return (
                <tr
                  key={pos.isin}
                  className='border-b border-border/50 hover:bg-bg-elevated/30 transition-colors group'
                >
                  <td className='p-4'>
                    <div className='font-black text-text tracking-tight group-hover:text-primary transition-colors'>
                      {pos.symbol}
                    </div>
                    <div className='text-[10px] font-bold text-text-muted uppercase tracking-tighter'>
                      Day {getOr(0, 'days_held')(pos)} · {pos.isin}
                    </div>
                  </td>
                  <td className='p-4 text-right font-mono text-text-muted'>
                    {getOr(
                      0,
                      'shares'
                    )(pos).toLocaleString(undefined, {
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className='p-4 text-right font-mono text-text-muted'>
                    ₹{getOr(0, 'cost_basis')(pos).toLocaleString()}
                  </td>
                  <td className='p-4 text-right font-mono font-bold text-text'>
                    ₹{getOr(0, 'last_price')(pos).toLocaleString()}
                  </td>
                  <td className='p-4 text-right font-mono font-black text-text'>
                    ₹
                    {getOr(
                      0,
                      'market_value'
                    )(pos).toLocaleString(undefined, {
                      maximumFractionDigits: 0,
                    })}
                  </td>
                  <td className={`p-4 text-right font-black ${pnlColor}`}>
                    {pnlPct >= 0 ? '+' : ''}
                    {pnlPct.toFixed(2)}%
                  </td>
                  <td className='p-4 text-right font-bold text-text-muted'>
                    {getOr(0, 'weight_pct')(pos).toFixed(1)}%
                  </td>
                  <td className='p-4 text-right font-mono text-text-muted'>
                    {pos.composite_score != null
                      ? pos.composite_score.toFixed(3)
                      : '—'}
                  </td>
                  <td
                    className={`p-4 text-right font-mono font-bold ${
                      pos.target_weight == null
                        ? 'text-text-muted'
                        : pos.target_weight - getOr(0, 'weight_pct')(pos) > 0.05
                          ? 'text-bearish'
                          : pos.target_weight - getOr(0, 'weight_pct')(pos) <
                              -0.05
                            ? 'text-bullish'
                            : 'text-text-muted'
                    }`}
                  >
                    {pos.target_weight != null
                      ? (() => {
                          const drift =
                            pos.target_weight - getOr(0, 'weight_pct')(pos);
                          return `${drift >= 0 ? '+' : ''}${drift.toFixed(1)}%`;
                        })()
                      : '—'}
                  </td>
                  <td className='p-4 text-text-muted font-medium'>
                    {formatDisplayDate(pos.entry_date)}
                  </td>
                </tr>
              );
            })(positions)}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const SIDE_STYLES = {
  buy: 'bg-bullish/10 text-bullish border-bullish/20',
  sell: 'bg-bearish/10 text-bearish border-bearish/20',
  trim: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
};

// Event-reason badge taxonomy (V11.4 + force_exit). force_exit = a 07 terminated-name
// liquidation (merged/delisted), surfaced so the log shows every real exit.
const REASON_STYLES = {
  rebalance: {
    label: 'Rebalance',
    className: 'bg-primary/10 text-primary border-primary/20',
  },
  catastrophic_stop: {
    label: 'Catastrophic Stop',
    className: 'bg-bearish/10 text-bearish border-bearish/20',
  },
  force_exit: {
    label: 'Force Exit',
    className: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  },
};

// Signed qty-change cell: leading number is the pre-trade holding, paren is the change
// the fill applies (buy = +, sell/trim = −). e.g. a trim → "10 (-2)", a full exit →
// "25 (-25)", a fresh entry → "0 (+25)". Legacy rows (no holding_before) fall back to
// the signed change alone.
const QtyChange = ({ side, qty, holdingBefore }) => {
  const q = getOr(0, 'qty')({ qty });
  const sign = side === 'buy' ? '+' : '-';
  const deltaColor = side === 'buy' ? 'text-bullish' : 'text-bearish';
  const fmt = (n) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return (
    <span>
      {holdingBefore != null && (
        <span className='text-text-muted'>{fmt(holdingBefore)} </span>
      )}
      <span className={`font-bold ${deltaColor}`}>
        ({sign}
        {fmt(q)})
      </span>
    </span>
  );
};

// Rebalance log (specs/v3/11 V11.6 #3): events grouped by decision date (newest
// first), each expanding to its fills. Reads the pending-fills queue — no engine
// change. The reason badge is rebalance | catastrophic_stop (taxonomy asserted
// backend-side, V11.4).
const RebalanceLog = ({ events }) => {
  const [openDate, setOpenDate] = useState(null);

  if (isEmpty(events)) {
    return (
      <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm'>
        <h3 className='text-lg font-black flex items-center gap-3 mb-6 text-text uppercase tracking-tight'>
          <Repeat size={20} className='text-primary' /> Rebalance Log
        </h3>
        <div className='flex flex-col items-center justify-center py-12 text-center'>
          <Repeat size={40} className='text-text-muted mb-3 opacity-20' />
          <p className='text-text-muted max-w-xs'>
            No rebalances queued yet. Events appear here on each monthly
            rebalance (or a catastrophic stop).
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm'>
      <h3 className='text-lg font-black flex items-center gap-3 p-6 pb-4 text-text uppercase tracking-tight border-b border-border'>
        <Repeat size={20} className='text-primary' /> Rebalance Log
      </h3>
      <div className='divide-y divide-border/50'>
        {map((ev) => {
          const isOpen = openDate === ev.decision_date;
          const badge = REASON_STYLES[ev.reason] || REASON_STYLES.rebalance;
          // Regime-off when the overlay scaled below full deployment on the decision
          // day. Only meaningful on a rebalance (the day the fraction is consumed).
          const isRiskOff =
            ev.reason === 'rebalance' &&
            ev.deployable_fraction != null &&
            ev.deployable_fraction < 1;
          return (
            <div key={ev.decision_date}>
              <button
                onClick={() => setOpenDate(isOpen ? null : ev.decision_date)}
                className='w-full flex items-center justify-between gap-4 p-4 hover:bg-bg-elevated/30 transition-colors text-left'
              >
                <div className='flex items-center gap-3 flex-wrap'>
                  {isOpen ? (
                    <ChevronDown size={16} className='text-text-muted' />
                  ) : (
                    <ChevronRight size={16} className='text-text-muted' />
                  )}
                  <span className='font-black text-text tracking-tight'>
                    {formatDisplayDate(ev.decision_date)}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                  {isRiskOff && (
                    <span className='px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border bg-bearish/10 text-bearish border-bearish/20'>
                      Risk-Off · {(ev.deployable_fraction * 100).toFixed(0)}%
                      deployed
                    </span>
                  )}
                </div>
                <div className='flex items-center gap-3 text-[10px] font-black uppercase tracking-wider'>
                  <span className='text-bullish'>{ev.n_buys} buy</span>
                  <span className='text-bearish'>{ev.n_sells} sell</span>
                  <span className='text-amber-500'>{ev.n_trims} trim</span>
                  <span className='text-text-muted font-mono'>
                    ₹
                    {getOr(
                      0,
                      'total_cost_rupees'
                    )(ev).toLocaleString(undefined, {
                      maximumFractionDigits: 0,
                    })}{' '}
                    cost
                  </span>
                </div>
              </button>
              {isOpen && (
                <div className='overflow-x-auto bg-bg-elevated/20'>
                  <table className='w-full border-collapse'>
                    <thead>
                      <tr className='text-[9px] uppercase tracking-widest text-text-muted font-black border-b border-border/50'>
                        <th className='text-left p-3 pl-12'>Symbol</th>
                        <th className='text-left p-3'>Side</th>
                        <th className='text-right p-3'>Qty (Δ)</th>
                        <th className='text-right p-3'>Decision →&nbsp;Fill</th>
                        <th className='text-right p-3'>Cost</th>
                        <th className='text-left p-3'>Status</th>
                      </tr>
                    </thead>
                    <tbody className='text-xs'>
                      {map((f) => (
                        <tr
                          key={`${f.isin}-${f.side}`}
                          className='border-b border-border/30'
                        >
                          <td className='p-3 pl-12'>
                            <div className='font-black text-text'>
                              {f.symbol}
                            </div>
                            <div className='text-[9px] font-bold text-text-muted uppercase tracking-tighter'>
                              {f.isin}
                            </div>
                          </td>
                          <td className='p-3'>
                            <span
                              className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-widest border ${
                                SIDE_STYLES[f.side] ||
                                'bg-bg-elevated text-text-muted border-border'
                              }`}
                            >
                              {f.side}
                            </span>
                          </td>
                          <td className='p-3 text-right font-mono text-text-muted'>
                            <QtyChange
                              side={f.side}
                              qty={f.qty}
                              holdingBefore={f.holding_before}
                            />
                          </td>
                          <td className='p-3 text-right font-mono text-text-muted'>
                            ₹
                            {f.decision_price != null
                              ? f.decision_price.toLocaleString(undefined, {
                                  maximumFractionDigits: 2,
                                })
                              : '—'}{' '}
                            →{' '}
                            <span className='font-bold text-text'>
                              ₹
                              {f.fill_price != null
                                ? f.fill_price.toLocaleString(undefined, {
                                    maximumFractionDigits: 2,
                                  })
                                : '—'}
                            </span>
                          </td>
                          <td className='p-3 text-right font-mono text-text-muted'>
                            ₹
                            {f.cost_rupees != null
                              ? f.cost_rupees.toLocaleString(undefined, {
                                  maximumFractionDigits: 0,
                                })
                              : '—'}
                          </td>
                          <td className='p-3'>
                            <span
                              className={`text-[9px] font-black uppercase tracking-widest ${
                                f.status === 'filled'
                                  ? 'text-bullish'
                                  : 'text-amber-500'
                              }`}
                            >
                              {f.status}
                            </span>
                          </td>
                        </tr>
                      ))(getOr([], 'fills')(ev))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })(events)}
      </div>
    </div>
  );
};

export default S3PaperBook;
