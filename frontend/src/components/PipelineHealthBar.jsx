import React from 'react';

const PipelineHealthBar = ({ lastRun, fetched, scored, failures }) => {
  return (
    <div className=\"pipeline-health\">
      <p>Last Run: {lastRun}</p>
      <p>Stocks Fetched: {fetched}</p>
      <p>Stocks Scored: {scored}</p>
      <p>Fetch Failures: {failures}</p>
    </div>
  );
};

export default PipelineHealthBar;
