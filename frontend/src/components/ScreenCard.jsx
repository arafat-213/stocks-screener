import React from 'react';
import './ScreenCard.css';

const ScreenCard = ({ screen, isSelected, onClick }) => {
  const badgeClass = screen.category.toLowerCase().replace(' ', '-');
  
  return (
    <div 
      className={`screen-card ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <span className={`screen-card-badge ${badgeClass}`}>
        {screen.category}
      </span>
      <h3>{screen.label}</h3>
      <p>{screen.description}</p>
    </div>
  );
};

export default ScreenCard;
