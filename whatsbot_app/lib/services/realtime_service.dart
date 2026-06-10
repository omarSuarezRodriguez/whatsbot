import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/api_config.dart';
import '../models/realtime_event.dart';
import 'api_client.dart';

/// WebSocket tiempo real — sesión persistente estilo WhatsApp.
///
/// - Socket único con keepalive (ping + watchdog)
/// - Sync REST solo al reconectar / volver a primer plano (sin polling)
/// - Persistencia SQLite antes de notificar a la UI
class RealtimeService {
  RealtimeService._();

  static final RealtimeService instance = RealtimeService._();

  static const Duration _ackTimeout = Duration(seconds: 15);
  static const Duration _clientPingInterval = Duration(seconds: 25);
  static const Duration _watchdogInterval = Duration(seconds: 45);
  static const Duration _staleConnection = Duration(seconds: 90);

  final StreamController<RealtimeEvent> _events =
      StreamController<RealtimeEvent>.broadcast();
  final StreamController<bool> _connectionState =
      StreamController<bool>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  Timer? _ackTimeoutTimer;
  Timer? _clientPingTimer;
  Timer? _watchdogTimer;
  Completer<void>? _connectedCompleter;

  bool _intentionalDisconnect = false;
  bool _connecting = false;
  bool _connected = false;
  int _backoffSeconds = 1;
  DateTime? _lastActivityAt;
  DateTime? _lastSyncAt;

  /// Evita abrir WebSocket real en widget tests.
  bool disableSocketForTesting = false;

  /// Sync incremental al reconectar (delegado a SyncEngine).
  Future<void> Function()? onReconnectSync;

  /// Persiste evento WS en SQLite antes de emitirlo a la UI.
  Future<void> Function(RealtimeEvent event)? persistEvent;

  /// Si devuelve false, se omite sync al recibir frame `connected`.
  bool Function()? shouldSyncOnConnect;

  Stream<RealtimeEvent> get events => _events.stream;

  Stream<bool> get connectionState => _connectionState.stream;

  bool get isConnected => _connected;

  /// Inicia o restablece la sesión WS (login, cold start, vuelta de red).
  Future<void> connect() async {
    if (!apiClient.isLoggedIn || disableSocketForTesting) return;
    _intentionalDisconnect = false;
    _reconnectTimer?.cancel();
    await _openSocket();
    _startKeepAlive();
  }

  /// Espera hasta que el servidor confirme `connected` (o timeout).
  Future<bool> waitUntilConnected({
    Duration timeout = const Duration(seconds: 20),
  }) async {
    if (_connected) return true;
    if (disableSocketForTesting) return false;
    _connectedCompleter ??= Completer<void>();
    try {
      await _connectedCompleter!.future.timeout(timeout);
      return _connected;
    } on TimeoutException {
      return false;
    } finally {
      _connectedCompleter = null;
    }
  }

  void markSyncCompleted() {
    _lastSyncAt = DateTime.now();
  }

  /// Reconecta y sincroniza al volver a primer plano (patrón WhatsApp).
  Future<void> onAppResumed() async {
    if (!apiClient.isLoggedIn || disableSocketForTesting) return;
    _intentionalDisconnect = false;
    _backoffSeconds = 1;
    _connecting = false;
    if (!_connected) {
      await _openSocket();
    }
    _startKeepAlive();
    await _syncAfterReconnect(force: true);
  }

  /// Fuerza reconexión si la sesión quedó colgada.
  Future<void> ensureConnected() async {
    if (!apiClient.isLoggedIn || disableSocketForTesting) return;
    if (_connected) return;
    _intentionalDisconnect = false;
    if (_connecting) {
      final stale = _lastActivityAt;
      if (stale != null &&
          DateTime.now().difference(stale) < _ackTimeout) {
        return;
      }
      _connecting = false;
    }
    _reconnectTimer?.cancel();
    await _openSocket();
    _startKeepAlive();
  }

  Future<void> disconnect() async {
    _intentionalDisconnect = true;
    _stopKeepAlive();
    _reconnectTimer?.cancel();
    _releaseConnectedCompleter();
    await _subscription?.cancel();
    _subscription = null;
    await _safeCloseChannel();
    _connecting = false;
    _setConnected(false);
  }

  Future<void> syncNow() async {
    await _syncAfterReconnect(force: true);
  }

  void sendTyping({required int conversationId, required bool isTyping}) {
    _sendJson({
      'type': isTyping ? 'typing.start' : 'typing.stop',
      'conversation_id': conversationId,
    });
  }

  Future<void> _openSocket() async {
    if (_intentionalDisconnect || !apiClient.isLoggedIn) return;
    if (_connecting) return;

    final token = apiClient.accessToken;
    if (token == null || token.isEmpty) return;

    _connecting = true;
    _ackTimeoutTimer?.cancel();
    _ackTimeoutTimer = Timer(_ackTimeout, () {
      if (_connecting && !_connected) {
        _forceReconnect();
      }
    });

    await _subscription?.cancel();
    _subscription = null;
    await _safeCloseChannel();
    _setConnected(false);

    try {
      final uri = Uri.parse(
        '${ApiConfig.wsBaseUrl}/whatsbot/ws?token=${Uri.encodeComponent(token)}',
      );
      final channel = IOWebSocketChannel.connect(
        uri,
        headers: ApiConfig.connectionHeaders,
      );
      _channel = channel;
      _touchActivity();
      _subscription = channel.stream.listen(
        _onData,
        onError: (_) => _forceReconnect(),
        onDone: _forceReconnect,
        cancelOnError: true,
      );
    } catch (_) {
      _connecting = false;
      _ackTimeoutTimer?.cancel();
      _scheduleReconnect();
    }
  }

  void _onData(dynamic data) {
    _touchActivity();

    Map<String, dynamic>? map;
    try {
      final decoded = jsonDecode(data as String);
      if (decoded is Map<String, dynamic>) {
        map = decoded;
      } else if (decoded is Map) {
        map = Map<String, dynamic>.from(decoded);
      }
    } catch (_) {
      return;
    }
    if (map == null) return;

    final type = map['type'] as String? ?? '';
    if (type == 'ping') {
      _sendJson({'type': 'pong'});
      return;
    }
    if (type == 'connected') {
      _ackTimeoutTimer?.cancel();
      _connecting = false;
      _backoffSeconds = 1;
      _setConnected(true);
      _connectedCompleter?.complete();
      _connectedCompleter = null;
      unawaited(_syncAfterReconnect());
      return;
    }
    if (type == 'pong') {
      return;
    }

    final event = RealtimeEvent.fromJson(map);
    _emitAfterPersist(event);
  }

  void _emitAfterPersist(RealtimeEvent event) {
    unawaited(emitAfterPersist(event));
  }

  /// Persiste en SQLite (si hay handler) y emite a listeners de UI.
  Future<void> emitAfterPersist(RealtimeEvent event) async {
    final persist = persistEvent;
    if (persist == null) {
      if (!_events.isClosed) _events.add(event);
      return;
    }

    try {
      await persist(event);
    } catch (_) {
      // La UI recibe el evento aunque falle SQLite.
    }
    if (!_events.isClosed) _events.add(event);
  }

  /// Emula un frame WS en tests (misma ruta que `_onData`).
  Future<void> debugEmitEvent(RealtimeEvent event) => emitAfterPersist(event);

  /// Fija estado de conexión en tests sin abrir socket real.
  void debugSetConnected(bool value) => _setConnected(value);

  void _forceReconnect() {
    _ackTimeoutTimer?.cancel();
    _connecting = false;
    _setConnected(false);
    _releaseConnectedCompleter();
    _subscription?.cancel();
    _subscription = null;
    unawaited(_safeCloseChannel());
    _scheduleReconnect();
  }

  void _releaseConnectedCompleter() {
    final completer = _connectedCompleter;
    _connectedCompleter = null;
    if (completer != null && !completer.isCompleted) {
      completer.complete();
    }
  }

  Future<void> _safeCloseChannel() async {
    final channel = _channel;
    _channel = null;
    if (channel == null) return;
    try {
      await channel.sink.close(ws_status.normalClosure);
    } catch (_) {}
  }

  void _scheduleReconnect() {
    if (_intentionalDisconnect || !apiClient.isLoggedIn) return;
    _reconnectTimer?.cancel();
    final delay = Duration(seconds: _backoffSeconds);
    _backoffSeconds = (_backoffSeconds * 2).clamp(1, 30);
    _reconnectTimer = Timer(delay, () {
      unawaited(_openSocket());
    });
  }

  void _setConnected(bool value) {
    if (_connected == value) return;
    _connected = value;
    _connectionState.add(value);
  }

  void _touchActivity() {
    _lastActivityAt = DateTime.now();
  }

  void _startKeepAlive() {
    if (disableSocketForTesting) return;
    _clientPingTimer?.cancel();
    _clientPingTimer = Timer.periodic(_clientPingInterval, (_) {
      if (!_connected || _intentionalDisconnect) return;
      _sendJson({'type': 'ping'});
    });

    _watchdogTimer?.cancel();
    _watchdogTimer = Timer.periodic(_watchdogInterval, (_) {
      if (_intentionalDisconnect || !apiClient.isLoggedIn) return;

      final last = _lastActivityAt;
      if (_connected &&
          last != null &&
          DateTime.now().difference(last) > _staleConnection) {
        _forceReconnect();
        return;
      }

      if (!_connected && (connectivityOnline?.call() ?? true)) {
        unawaited(ensureConnected());
      }
    });
  }

  void _stopKeepAlive() {
    _ackTimeoutTimer?.cancel();
    _clientPingTimer?.cancel();
    _watchdogTimer?.cancel();
  }

  /// Inyectable en tests; en producción usa ConnectivityService vía callback.
  bool Function()? connectivityOnline = () => true;

  void _sendJson(Map<String, dynamic> payload) {
    final channel = _channel;
    if (channel == null) return;
    try {
      channel.sink.add(jsonEncode(payload));
      _touchActivity();
    } catch (_) {}
  }

  Future<void> _syncAfterReconnect({bool force = false}) async {
    final sync = onReconnectSync;
    if (sync == null) return;

    if (!force) {
      final gate = shouldSyncOnConnect;
      if (gate != null && !gate()) return;
      final last = _lastSyncAt;
      if (last != null &&
          DateTime.now().difference(last) < const Duration(seconds: 3)) {
        return;
      }
    }

    try {
      await sync();
      markSyncCompleted();
    } catch (_) {
      // Sync silencioso; reconexión reintentará.
    }
  }
}

final realtimeService = RealtimeService.instance;
