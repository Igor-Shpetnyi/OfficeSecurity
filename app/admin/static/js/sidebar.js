// Мобільний off-canvas сайдбар (<= 768px, див. theme.css) — без нових залежностей.
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    var toggle = document.getElementById('menu-toggle');
    if (!sidebar || !backdrop || !toggle) return;

    function close() {
      sidebar.classList.remove('open');
      backdrop.classList.remove('open');
    }

    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('open');
      backdrop.classList.toggle('open');
    });

    backdrop.addEventListener('click', close);
  });
})();
