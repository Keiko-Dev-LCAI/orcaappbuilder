(function () {
  var cfg = window.ORCA_INTEGRATIONS || {};
  var dsn = (cfg.sentryDsn || '').trim();
  if (!dsn) return;

  var s = document.createElement('script');
  s.src = 'https://browser.sentry-cdn.com/8.47.0/bundle.min.js';
  s.crossOrigin = 'anonymous';
  s.onload = function () {
    if (!window.Sentry) return;
    window.Sentry.init({
      dsn: dsn,
      environment: 'production',
      release: cfg.appName || 'orca-app',
      tracesSampleRate: 0.05,
    });
    window.addEventListener('unhandledrejection', function (e) {
      if (e.reason) window.Sentry.captureException(e.reason);
    });
  };
  document.head.appendChild(s);
})();