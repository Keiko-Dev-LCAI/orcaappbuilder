(function () {
  var cfg = window.ORCA_INTEGRATIONS || {};
  if (cfg.enableServiceWorker === false) return;
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('./sw.js').catch(function () {});
  });
})();