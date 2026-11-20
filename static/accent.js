const accentPicker = document.getElementById('calendarAccent');
const accentKey = 'pianissimo.calendarAccent';
try {
  const saved = localStorage.getItem(accentKey);
  if (Array.from(accentPicker.options).some(option => option.value === saved)) {
    accentPicker.value = saved;
  }
} catch {
  // The picker also works when browser storage is disabled.
}
document.documentElement.dataset.accent = accentPicker.value;
accentPicker.addEventListener('change', () => {
  document.documentElement.dataset.accent = accentPicker.value;
  try {
    localStorage.setItem(accentKey, accentPicker.value);
  } catch {
    // Keep the selection for this visit.
  }
});
