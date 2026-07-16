// Anti-flash уже застосований inline-скриптом у <head> (base.html).
// Тут лише toggle-логіка — design.md §8, без React.
(function () {
  function getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  }

  function setTheme(theme) {
    document.documentElement.classList.add('theme-transitioning');
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    window.setTimeout(function () {
      document.documentElement.classList.remove('theme-transitioning');
    }, 200);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', function () {
      setTheme(getTheme() === 'dark' ? 'light' : 'dark');
    });
  });
})();
