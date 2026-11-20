(() => {
  try {
    const theme = localStorage.getItem('pianissimo.calendarTheme');
    const accent = localStorage.getItem('pianissimo.calendarAccent');
    if (['light', 'dark', 'system'].includes(theme)) document.documentElement.dataset.theme = theme;
    if (['lime','sage','slate','plum','clay','violet','teal','rose','amber'].includes(accent)) document.documentElement.dataset.accent = accent;
  } catch { /* Appearance controls also work without persistent storage. */ }
})();
