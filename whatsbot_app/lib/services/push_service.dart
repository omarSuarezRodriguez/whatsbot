import 'dart:async' show StreamSubscription, unawaited;
import 'dart:io' show Platform;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import '../di/app_services.dart';
import 'api_client.dart';
import 'message_alerts_service.dart';

/// Handler FCM en background (proceso aislado).
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
}

/// Push FCM/APNs — Fase 11.4.
///
/// Si Firebase no está configurado en el proyecto, degrada sin romper la app.
class PushService {
  PushService._();

  static final PushService instance = PushService._();

  bool _available = false;
  String? _currentToken;
  String _platform = 'android';
  StreamSubscription<String>? _tokenRefreshSub;

  bool get isAvailable => _available;

  String? get currentToken => _currentToken;

  Future<void> init() async {
    if (_available) return;
    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(
        firebaseMessagingBackgroundHandler,
      );
      _available = true;
      await _configureMessaging();
    } catch (e) {
      if (kDebugMode) {
        debugPrint('PushService: Firebase no configurado ($e)');
      }
    }
  }

  Future<void> _configureMessaging() async {
    final messaging = FirebaseMessaging.instance;
    await messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );
    await messaging.setForegroundNotificationPresentationOptions(
      alert: true,
      badge: true,
      sound: true,
    );

    FirebaseMessaging.onMessage.listen(_onForegroundMessage);
    FirebaseMessaging.onMessageOpenedApp.listen(_onOpenFromNotification);

    final initial = await messaging.getInitialMessage();
    if (initial != null) {
      _onOpenFromNotification(initial);
    }

    _tokenRefreshSub ??= messaging.onTokenRefresh.listen((token) {
      unawaited(_registerToken(token));
    });
  }

  Future<void> registerAfterLogin() async {
    if (!_available) return;
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) {
        await _registerToken(token);
      }
    } catch (e) {
      if (kDebugMode) {
        debugPrint('PushService: no se pudo obtener token FCM: $e');
      }
    }
  }

  Future<void> unregisterOnLogout() async {
    final token = _currentToken;
    _tokenRefreshSub?.cancel();
    _tokenRefreshSub = null;
    _currentToken = null;
    if (!_available || token == null) return;
    try {
      await apiClient.unregisterDeviceToken(
        token: token,
        platform: _platform,
      );
    } catch (_) {}
    try {
      await FirebaseMessaging.instance.deleteToken();
    } catch (_) {}
  }

  Future<void> _registerToken(String token) async {
    _currentToken = token;
    _platform = Platform.isIOS ? 'ios' : 'android';
    await apiClient.registerDeviceToken(token: token, platform: _platform);
  }

  void _onForegroundMessage(RemoteMessage message) {
    final data = message.data;
    final type = data['type'] ?? '';
    if (type != 'message.new') return;

    final conversationId = int.tryParse(data['conversation_id'] ?? '');
    if (conversationId == null) return;

    final title = message.notification?.title ??
        data['title']?.toString() ??
        'Nuevo mensaje';
    final preview = message.notification?.body ??
        data['preview']?.toString() ??
        '';

    final messageId = int.tryParse(data['message_id'] ?? '') ??
        DateTime.now().millisecondsSinceEpoch;

    // Push implica WS caído: hidratar SQLite antes de alertar para actualizar la lista.
    unawaited(_handleIncomingPush(
      conversationId: conversationId,
      displayName: title,
      preview: preview,
      messageId: messageId,
    ));
  }

  void _onOpenFromNotification(RemoteMessage message) {
    final conversationId =
        int.tryParse(message.data['conversation_id'] ?? '');
    if (conversationId == null) return;
    unawaited(_syncConversationFromPush(conversationId));
    messageAlerts.onOpenConversation?.call(conversationId);
  }

  Future<void> _handleIncomingPush({
    required int conversationId,
    required String displayName,
    required String preview,
    required int messageId,
  }) async {
    await _syncConversationFromPush(conversationId);
    await messageAlerts.notifyFromPush(
      conversationId: conversationId,
      displayName: displayName,
      preview: preview,
      messageId: messageId,
    );
  }

  Future<void> _syncConversationFromPush(int conversationId) async {
    if (!AppServices.isInitialized) return;
    try {
      await AppServices.syncEngine.syncConversationsIncremental();
      await AppServices.syncEngine.syncMessagesIncremental(
        conversationId,
        force: true,
      );
    } catch (_) {
      // Degradación silenciosa: la caché local sigue disponible.
    }
  }
}

final pushService = PushService.instance;
