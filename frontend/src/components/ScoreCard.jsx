import React from 'react';

const ScoreCard = ({ symbol, daily, weekly, monthly }) => {
  return (
    <div className=\"score-card\">
      <h3>{symbol}</h3>
      <p>Daily: {daily}</p>
      <p>Weekly: {weekly}</p>
      <p>Monthly: {monthly}</p>
    </div>
  );
};

export default ScoreCard;
