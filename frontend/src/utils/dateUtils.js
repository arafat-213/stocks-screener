export const getISTDateString = (dateObj = new Date()) => {
  // Returns 'YYYY-MM-DD' formatted specifically for Asia/Kolkata
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(dateObj);
};

export const formatDisplayDate = (dateStr) => {
  // If no date, return empty
  if (!dateStr) return '';

  // Create a date object. If it's a naive YYYY-MM-DD from the DB,
  // appending T00:00:00Z ensures we treat the 'day' as absolute UTC
  // before converting to IST. If it's already an ISO string, it parses fine.
  const parsedDate = new Date(
    dateStr.includes('T') ? dateStr : `${dateStr}T00:00:00Z`
  );

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(parsedDate);
};
