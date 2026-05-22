const ScreenCard = ({ screen, isSelected, onClick }) => {
  const categoryClasses = {
    'momentum': 'text-amber-600 bg-amber-600/10',
    'value': 'text-blue-600 bg-blue-600/10',
    'price-action': 'text-teal-600 bg-teal-600/10',
    'quality': 'text-purple-600 bg-purple-600/10',
  };

  const badgeClass = categoryClasses[screen.category.toLowerCase().replace(' ', '-')] || 'text-text-muted bg-text-muted/10';
  
  return (
    <div 
      className={`bg-bg-secondary border rounded-lg p-4 cursor-pointer transition-all duration-200 flex flex-col gap-2 
        ${isSelected 
          ? 'border-bullish bg-bullish/5' 
          : 'border-border hover:border-text-muted'}`}
      onClick={onClick}
    >
      <span className={`self-start text-[11px] font-bold px-2 py-1 rounded-[6px] uppercase tracking-wider ${badgeClass}`}>
        {screen.category}
      </span>
      <h3 className="text-base font-bold text-text m-0">{screen.label}</h3>
      <p className="text-sm text-text-muted m-0 line-clamp-2">{screen.description}</p>
    </div>
  );
};

export default ScreenCard;
