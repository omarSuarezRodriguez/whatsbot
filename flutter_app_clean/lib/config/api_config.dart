/// URL del backend WhatsBot.
///
/// Cambia [_env] según dónde corras la app:
///   'emulator'  → Android Studio / AVD en la misma PC  (10.0.2.2:5000)
///   'simulator' → iPhone Simulator en la misma PC       (127.0.0.1:5000)
///   'ngrok'     → Dispositivo físico / Twilio webhook   (URL ngrok)
///
/// Luego haz hot-restart (r) en Flutter y listo.
class ApiConfig {
  ApiConfig._();

  static const _env = 'ngrok'; // ← CAMBIA ESTO

  static const _urls = {
    'emulator': 'http://10.0.2.2:5000',
    'simulator': 'http://127.0.0.1:5000',
    'ngrok': 'https://snowman-shower-pellet.ngrok-free.dev',
  };

  static String get apiBaseUrl => _urls[_env] ?? _urls['ngrok']!;

  /// Headers extra (ngrok muestra una advertencia en el navegador sin esto).
  static Map<String, String> get connectionHeaders {
    if (apiBaseUrl.contains('ngrok')) {
      return const {'ngrok-skip-browser-warning': 'true'};
    }
    return const {};
  }

  /// URL WebSocket derivada de [apiBaseUrl].
  static String get wsBaseUrl {
    final base = apiBaseUrl;
    if (base.startsWith('https://')) return 'wss://${base.substring(8)}';
    if (base.startsWith('http://')) return 'ws://${base.substring(7)}';
    return base;
  }
}
