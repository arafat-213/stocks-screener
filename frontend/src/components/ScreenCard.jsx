const ScreenCard = ({ screen, isSelected, onClick }) => {
  const categoryClasses = {
    momentum: 'bg-amber-500 text-white shadow-amber-500/20',
    value: 'bg-blue-500 text-white shadow-blue-500/20',
    'price-action': 'bg-green-500 text-white shadow-green-500/20',
    quality: 'bg-indigo-500 text-white shadow-indigo-500/20',
  };

  const badgeClass =
    categoryClasses[screen.category.toLowerCase().replace(' ', '-')] ||
    'bg-slate-500 text-white';

  return (
    <div
      className={`bg-bg-secondary border-2 rounded-2xl p-5 cursor-pointer transition-all duration-300 flex flex-col gap-3 shadow-sm
        ${
          isSelected
            ? 'border-blue-600 bg-blue-50 dark:bg-blue-900/10 shadow-lg shadow-blue-500/10'
            : 'border-border hover:border-blue-500/30 hover:-translate-y-1 hover:shadow-md'
        }`}
      onClick={onClick}
    >
      <span
        className={`self-start text-[9px] font-black px-2.5 py-1 rounded-lg uppercase tracking-[0.15em] shadow-sm ${badgeClass}`}
      >
        {screen.category}
      </span>
      <h3 className='text-lg font-black text-text m-0 tracking-tight'>
        {screen.label}
      </h3>
      <p className='text-xs font-bold text-slate-500 dark:text-slate-400 m-0 line-clamp-2 leading-relaxed uppercase tracking-tight'>
        {screen.description}
      </p>
    </div>
  );
};

export default ScreenCard;
