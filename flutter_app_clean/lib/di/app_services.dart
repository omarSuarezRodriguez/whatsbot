import 'dart:async' show TimeoutException, unawaited;

import '../data/local/app_database.dart';
import '../data/repositories/chat_repository.dart';
import '../data/repositories/message_repository.dart';
import '../data/sync/sync_engine.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../services/api_client.dart';
import '../services/connectivity_service.dart';
import '../services/message_alerts_service.dart';
import '../services/realtime_service.dart';

/// Inicialización de DB local, repositorios y motor de sync (OF-A / OF-B / OF-D).
class AppServices {
  AppServices._();

  static late AppDatabase database;
  static late ChatRepository chatRepository;
  static late MessageRepository messageRepository;
  static late SyncEngine syncEngine;

  static bool _initialized = false;
  static bool _hydratedThisSession = false;

  static bool get isInitialized => _initialized;

  static Future<void> init() async {
    if (_initialized) return;
    database = AppDatabase();
    chatRepository = ChatRepository(database, apiClient);
    messageRepository = MessageRepository(database, apiClient);
    syncEngine = SyncEngine(chatRepository, messageRepository);
    _wireRealtime();
    _wireConnectivity();
    await connectivityService.start();
    _initialized = true;
  }

  static void _wireRealtime() {
    realtimeService.onReconnectSync = syncEngine.syncOnReconnect;
    realtimeService.persistEvent = syncEngine.handleRealtimeEvent;
    realtimeService.connectivityOnline = () => connectivityService.isOnline;
    realtimeService.shouldSyncOnConnect = () => !_hydratedThisSession;
    syncEngine.onIncomingMessage = _onIncomingMessage;
  }

  static Future<void> _onIncomingMessage(
    Conversation conversation,
    ChatMessage message,
  ) {
    return messageAlerts.handleRealtimeMessage(
      conversation: conversation,
      message: message,
    );
  }

  static void _wireConnectivity() {
    connectivityService.onBackOnline = _onBackOnline;
  }

  static Future<void> _onBackOnline() async {
    if (!apiClient.isLoggedIn) return;
    await startRealtimeSession();
  }

  static Future<void> clearLocalData() async {
    if (!_initialized) return;
    _hydratedThisSession = false;
    await database.clearAll();
  }

  /// Login / cold start: REST hidrata caché + WS en segundo plano (sin bloquear UI).
  static Future<void> startRealtimeSession() async {
    if (!_initialized || !apiClient.isLoggedIn) return;

    // 1) Caché local desde REST; si falla, seguimos con SQLite
    await hydrateAfterLogin();

    // 2) Socket en segundo plano — la UI no espera `connected`
    unawaited(realtimeService.connect());
  }

  /// Vuelta a primer plano: reconectar WS + delta REST una vez.
  static Future<void> onAppResumed() async {
    if (!_initialized || !apiClient.isLoggedIn) return;
    await realtimeService.onAppResumed();
  }

  /// Cola saliente + sync incremental (una vez por sesión en login).
  static Future<void> hydrateAfterLogin() async {
    if (!_initialized) return;
    try {
      await syncEngine
          .syncOnReconnect()
          .timeout(const Duration(seconds: 15));
    } on TimeoutException {
      // API lenta o caída: mostrar caché local y reintentar al reconectar WS.
    } catch (_) {
      // Misma degradación: la app arranca con datos locales.
    }
    realtimeService.markSyncCompleted();
    _hydratedThisSession = true;
  }

  static void resetSessionFlags() {
    _hydratedThisSession = false;
  }

  static void stopForegroundFallback() {}
}
