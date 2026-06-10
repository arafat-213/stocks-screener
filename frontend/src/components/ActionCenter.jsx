import { AlertTriangle, Target, Zap, ChevronRight, Inbox } from 'lucide-react';

/**
 * ActionCard Component
 * A high-contrast, brutalist-style card for critical stock actions.
 */
const ActionCard = ({
  item,
  subtitle,
  variant,
  actionLabel,
  onAction,
  icon: Icon,
  isUrgent,
}) => {
  const { symbol } = item;
  const themes = {
    primary: {
      border: 'border-primary',
      bg: 'bg-primary',
      text: 'text-primary',
      shadow: 'hover:shadow-[4px_4px_0px_0px_rgba(59,130,246,0.5)]',
      lightBg: 'bg-primary/5',
    },
    bullish: {
      border: 'border-bullish',
      bg: 'bg-bullish',
      text: 'text-bullish',
      shadow: 'hover:shadow-[4px_4px_0px_0px_rgba(34,197,94,0.5)]',
      lightBg: 'bg-bullish/5',
    },
    bearish: {
      border: 'border-bearish',
      bg: 'bg-bearish',
      text: 'text-bearish',
      shadow: 'hover:shadow-[4px_4px_0px_0px_rgba(239,68,68,0.5)]',
      lightBg: 'bg-bearish/5',
    },
  };

  const theme = themes[variant] || themes.primary;

  return (
    <div
      className={`group relative p-4 border-2 ${theme.border} bg-bg-secondary ${theme.shadow} transition-all duration-200 animate-zoom-in overflow-hidden`}
    >
      {/* Urgent Indicator */}
      {isUrgent && (
        <div className='absolute -top-1 -right-1 flex h-4 w-4'>
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full ${theme.bg} opacity-75`}
          ></span>
          <span
            className={`relative inline-flex rounded-full h-4 w-4 ${theme.bg}`}
          ></span>
        </div>
      )}

      <div className='flex justify-between items-start mb-4'>
        <div className='flex flex-col'>
          <span className='text-[10px] uppercase tracking-[0.2em] text-text-muted font-bold mb-1'>
            Stock Symbol
          </span>
          <span className='text-3xl font-black tracking-tighter uppercase leading-none'>
            {symbol.split('.')[0]}
          </span>
          <span className='text-[10px] text-text-muted font-mono mt-1 opacity-70'>
            {symbol}
          </span>
        </div>
        <div className={`p-3 border-2 ${theme.border} ${theme.lightBg}`}>
          <Icon size={24} strokeWidth={2.5} className={theme.text} />
        </div>
      </div>

      <div className='space-y-4'>
        <div
          className={`py-2 px-3 border-l-4 ${theme.border} ${theme.lightBg}`}
        >
          <p className='text-xs font-bold uppercase tracking-wider text-text mb-0.5'>
            Status Update
          </p>
          <p className='text-sm font-medium leading-tight text-text-muted italic'>
            {subtitle}
          </p>
        </div>

        <button
          onClick={() => onAction(item)}
          className={`w-full py-3 px-4 border-2 ${theme.border} ${theme.bg} text-white font-black uppercase tracking-widest text-xs flex items-center justify-center gap-2 active:scale-95 transition-all hover:brightness-110 shadow-[2px_2px_0px_0px_rgba(0,0,0,0.2)]`}
        >
          {actionLabel}
          <ChevronRight size={16} strokeWidth={3} />
        </button>
      </div>
    </div>
  );
};

/**
 * ColumnHeader Component
 */
const ColumnHeader = ({ title, icon: Icon, colorClass }) => (
  <div
    className={`flex items-center gap-3 mb-6 p-3 border-b-4 ${colorClass} bg-bg-secondary`}
  >
    <Icon size={20} className={colorClass.replace('border-', 'text-')} />
    <h3 className='text-lg font-black uppercase tracking-tighter italic'>
      {title}
    </h3>
  </div>
);

/**
 * ActionCenter Component
 * Main dashboard for immediate trading actions and alerts.
 */
const ActionCenter = ({
  entry_candidates = [],
  sl_risk = [],
  target_near = [],
  onExecute,
  onExit,
}) => {
  const hasItems =
    entry_candidates.length > 0 || sl_risk.length > 0 || target_near.length > 0;

  if (!hasItems) return null;

  return (
    <section className='w-full mb-12 animate-fade-in'>
      <div className='flex items-center gap-4 mb-8'>
        <div className='h-[2px] flex-grow bg-border'></div>
        <h2 className='text-sm font-black uppercase tracking-[0.4em] text-text-muted flex items-center gap-2'>
          <Zap size={16} className='text-primary fill-primary' />
          Action Center
        </h2>
        <div className='h-[2px] flex-grow bg-border'></div>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 items-start'>
        {/* Entry Candidates Column */}
        <div className='space-y-4'>
          <ColumnHeader
            title='Entry Candidates'
            icon={Zap}
            colorClass='border-primary'
          />
          {entry_candidates.length > 0 ? (
            entry_candidates.map((item) => (
              <ActionCard
                key={item.symbol}
                item={item}
                subtitle={`₹${item.current_price} (Zone: ${item.entry_low}-${item.entry_high})`}
                variant='bullish'
                icon={Zap}
                actionLabel='Execute Order'
                onAction={onExecute}
                isUrgent={
                  Math.abs(item.current_price - item.entry_low) /
                    item.entry_low <=
                    0.0025 ||
                  Math.abs(item.current_price - item.entry_high) /
                    item.entry_high <=
                    0.0025
                }
              />
            ))
          ) : (
            <div className='p-8 border-2 border-dashed border-border bg-bg-secondary/50 flex flex-col items-center justify-center text-center opacity-60'>
              <Inbox size={24} className='mb-2 text-text-muted' />
              <p className='text-xs uppercase tracking-widest font-bold italic'>
                No entries pending
              </p>
            </div>
          )}
        </div>

        {/* SL Risk Column */}
        <div className='space-y-4'>
          <ColumnHeader
            title='Risk Management'
            icon={AlertTriangle}
            colorClass='border-bearish'
          />
          {sl_risk.length > 0 ? (
            sl_risk.map((item) => (
              <ActionCard
                key={item.id}
                item={item}
                subtitle={`₹${item.current_price} vs SL ₹${item.stop_loss} (${item.dist_pct}%)`}
                variant='bearish'
                icon={AlertTriangle}
                actionLabel='Manage Exit'
                onAction={onExit}
                isUrgent={Math.abs(item.dist_pct) <= 0.25}
              />
            ))
          ) : (
            <div className='p-8 border-2 border-dashed border-border bg-bg-secondary/50 flex flex-col items-center justify-center text-center opacity-60'>
              <Inbox size={24} className='mb-2 text-text-muted' />
              <p className='text-xs uppercase tracking-widest font-bold italic'>
                Risk levels clear
              </p>
            </div>
          )}
        </div>

        {/* Near Targets Column */}
        <div className='space-y-4'>
          <ColumnHeader
            title='Target Alerts'
            icon={Target}
            colorClass='border-bullish'
          />
          {target_near.length > 0 ? (
            target_near.map((item) => (
              <ActionCard
                key={item.id}
                item={item}
                subtitle={`₹${item.current_price} vs Tgt ₹${item.target} (${item.dist_pct}%)`}
                variant='bullish'
                icon={Target}
                actionLabel='Book Profit'
                onAction={onExit}
                isUrgent={Math.abs(item.dist_pct) <= 0.25}
              />
            ))
          ) : (
            <div className='p-8 border-2 border-dashed border-border bg-bg-secondary/50 flex flex-col items-center justify-center text-center opacity-60'>
              <Inbox size={24} className='mb-2 text-text-muted' />
              <p className='text-xs uppercase tracking-widest font-bold italic'>
                No targets reached
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default ActionCenter;
