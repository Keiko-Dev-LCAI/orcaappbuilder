(function () {
  // Single bump point with sw.js ORCA_SW_VERSION — keep these equal on every ship
  var ORCA_SW_VERSION = '9';
  var cfg = window.ORCA_INTEGRATIONS || {};
  if (cfg.enableServiceWorker === false) return;
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('./sw.js?v=' + ORCA_SW_VERSION).catch(function () {});
  });
})();
