import './Slider.css';

const Slider = ({ value, onChange, min = 0, max = 100, label, className = "" }) => {
  return (
    <div className={`custom-slider-container ${className}`}>
      {label && (
        <div className="slider-header">
          <label className="slider-label">{label}</label>
          <span className="slider-value mono">{value}</span>
        </div>
      )}
      <input 
        type="range" 
        min={min} 
        max={max} 
        value={value} 
        onChange={(e) => onChange(parseInt(e.target.value))}
        className="custom-range-input"
      />
      <div className="slider-track-fill" style={{ width: `${((value - min) / (max - min)) * 100}%` }}></div>
    </div>
  );
};

export default Slider;
