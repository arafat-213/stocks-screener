import { memo } from 'react';
import './Toggle.css';

const Toggle = memo(({ checked, onChange, label, icon: Icon }) => {
  return (
    <div className="toggle-wrapper" onClick={() => onChange(!checked)}>
      <div className="toggle-info">
        {Icon && <Icon size={14} className="toggle-icon" />}
        <span className="toggle-label">{label}</span>
      </div>
      <div className={`toggle-switch ${checked ? 'checked' : ''}`}>
        <div className="toggle-thumb" />
      </div>
    </div>
  );
});

export default Toggle;
