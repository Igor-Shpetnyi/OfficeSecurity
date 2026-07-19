// Періодично підвантажує HTML-фрагмент і підміняє вміст контейнера —
// без повного перезавантаження сторінки, без нових залежностей (без HTMX/React).
(function () {
  function startLiveRefresh(containerId, url, intervalMs) {
    var container = document.getElementById(containerId);
    if (!container) return;

    function refresh() {
      // <details data-key> (розгорнутий довгий текст, історія редагувань,
      // ланцюжок відповідей) інакше миттєво згортається щоразу після
      // заміни innerHTML — запам'ятовуємо відкриті ключі й відновлюємо їх
      // у щойно підставленому HTML.
      var openKeys = Array.prototype.slice
        .call(container.querySelectorAll('details[open][data-key]'))
        .map(function (d) { return d.dataset.key; });

      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (html === null) return;
          container.innerHTML = html;
          openKeys.forEach(function (key) {
            var d = container.querySelector('details[data-key="' + key + '"]');
            if (d) d.open = true;
          });
        })
        .catch(function () {
          // мовчки пропускаємо один цикл — наступний спробує знову
        });
    }

    setInterval(refresh, intervalMs);
  }

  window.startLiveRefresh = startLiveRefresh;
})();
