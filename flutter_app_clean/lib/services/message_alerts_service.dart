import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../di/app_services.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import 'api_client.dart';

/// Sonido + notificaciones locales al estilo WhatsApp cuando llega un mensaje entrante.
class MessageAlertsService {
  MessageAlertsService._();

  static final MessageAlertsService instance = MessageAlertsService._();

  static const _channelId = 'whatsbot_messages';
  static const _channelName = 'Mensajes';
  static const _soundAsset = 'sounds/incoming_message.wav';

  final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();
  final AudioPlayer _player = AudioPlayer();
  final Set<int> _notifiedMessageIds = {};
  final Set<int> _unreadConversationIds = {};
  final Map<int, int> _maxMessageIdByConversation = {};
  final Map<int, DateTime?> _lastMessageAtByConversation = {};
  bool _ready = false;
  bool _seeded = false;
  bool _appInForeground = true;
  int? _activeConversationId;
  void Function(int conversationId)? onOpenConversation;

  bool get appInForeground => _appInForeground;

  int? get activeConversationId => _activeConversationId;

  bool isConversationUnread(Conversation conversation) {
    if (_unreadConversationIds.contains(conversation.id)) return true;

    final lastAt = conversation.lastMessageAt;
    if (lastAt == null) return false;
    if (_activeConversationId == conversation.id && _appInForeground) {
      return false;
    }
    final seenAt =
        conversation.lastSeenAt ?? _lastSeenAtByConversation[conversation.id];
    if (seenAt == null) return true;
    return lastAt.isAfter(seenAt);
  }

  final Map<int, DateTime> _lastSeenAtByConversation = {};

  Future<void> init() async {
    if (_ready) return;

    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosInit = DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
    );
    await _notifications.initialize(
      const InitializationSettings(android: androidInit, iOS: iosInit),
      onDidReceiveNotificationResponse: _onNotificationTap,
    );

    final androidPlugin =
        _notifications.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
    await androidPlugin?.createNotificationChannel(
      const AndroidNotificationChannel(
        _channelId,
        _channelName,
        description: 'Avisos de mensajes nuevos de clientes',
        importance: Importance.max,
        playSound: true,
        enableVibration: true,
        showBadge: true,
        sound: RawResourceAndroidNotificationSound('incoming_message'),
      ),
    );

    await _requestPermissions();
    await _player.setReleaseMode(ReleaseMode.stop);
    _ready = true;
  }

  Future<void> _requestPermissions() async {
    final androidPlugin =
        _notifications.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
    await androidPlugin?.requestNotificationsPermission();

    final iosPlugin = _notifications.resolvePlatformSpecificImplementation<
        IOSFlutterLocalNotificationsPlugin>();
    await iosPlugin?.requestPermissions(alert: true, badge: true, sound: true);
  }

  void setAppInForeground(bool inForeground) {
    _appInForeground = inForeground;
  }

  void setActiveConversation(int? conversationId) {
    _activeConversationId = conversationId;
  }

  void markConversationSeen(int conversationId, {DateTime? at}) {
    _unreadConversationIds.remove(conversationId);
    final when = at ?? DateTime.now();
    _lastSeenAtByConversation[conversationId] = when;
    if (AppServices.isInitialized) {
      unawaited(AppServices.chatRepository.markSeen(conversationId, when));
    }
  }

  void markConversationUnread(int conversationId) {
    if (_activeConversationId == conversationId && _appInForeground) return;
    _unreadConversationIds.add(conversationId);
  }

  Future<void> notifyFromPush({
    required int conversationId,
    required String displayName,
    required String preview,
    required int messageId,
  }) async {
    await _notifyIncoming(
      conversationId: conversationId,
      displayName: displayName,
      preview: preview,
      messageId: messageId,
    );
  }

  Future<void> handleRealtimeMessage({
    required Conversation conversation,
    required ChatMessage message,
  }) async {
    if (!_ready || message.isOutgoing) return;

    final conversationId = conversation.id;
    final prevMax = _maxMessageIdByConversation[conversationId] ?? 0;
    if (message.id <= prevMax) return;

    _maxMessageIdByConversation[conversationId] = message.id;
    if (conversation.lastMessageAt != null) {
      _lastMessageAtByConversation[conversationId] = conversation.lastMessageAt;
    }

    markConversationUnread(conversationId);

    await _notifyIncoming(
      conversationId: conversationId,
      displayName: conversation.displayName,
      preview: message.body,
      messageId: message.id,
    );

    if (_activeConversationId == conversationId && _appInForeground) {
      markConversationSeen(
        conversationId,
        at: conversation.lastMessageAt ?? message.createdAt,
      );
    }
  }

  Future<void> handleChatMessages({
    required int conversationId,
    required String displayName,
    required List<ChatMessage> messages,
  }) async {
    if (!_ready || messages.isEmpty) return;

    final maxId = messages.map((m) => m.id).reduce((a, b) => a > b ? a : b);
    final prevMax = _maxMessageIdByConversation[conversationId];

    if (prevMax == null) {
      _maxMessageIdByConversation[conversationId] = maxId;
      final latestAt = messages
          .map((m) => m.createdAt)
          .reduce((a, b) => a.isAfter(b) ? a : b);
      markConversationSeen(conversationId, at: latestAt);
      _seeded = true;
      return;
    }

    final incoming = messages
        .where((m) => m.id > prevMax && !m.isOutgoing)
        .toList()
      ..sort((a, b) => a.id.compareTo(b.id));

    _maxMessageIdByConversation[conversationId] = maxId;

    for (final message in incoming) {
      markConversationUnread(conversationId);
      await _notifyIncoming(
        conversationId: conversationId,
        displayName: displayName,
        preview: message.body,
        messageId: message.id,
      );
    }

    if (_activeConversationId == conversationId && _appInForeground) {
      final latestAt = messages
          .map((m) => m.createdAt)
          .reduce((a, b) => a.isAfter(b) ? a : b);
      markConversationSeen(conversationId, at: latestAt);
    }
  }

  Future<void> handleConversations(List<Conversation> conversations) async {
    if (!_ready) return;

    if (!_seeded) {
      for (final conv in conversations) {
        _lastMessageAtByConversation[conv.id] = conv.lastMessageAt;
        markConversationSeen(
          conv.id,
          at: conv.lastSeenAt ?? conv.lastMessageAt,
        );
        if (AppServices.isInitialized) {
          unawaited(_seedMaxMessageId(conv.id));
        }
      }
      _seeded = true;
      return;
    }

    for (final conv in conversations) {
      final prevAt = _lastMessageAtByConversation[conv.id];
      final changed = conv.lastMessageAt != null &&
          (prevAt == null || conv.lastMessageAt!.isAfter(prevAt));
      _lastMessageAtByConversation[conv.id] = conv.lastMessageAt;

      if (!changed || conv.lastMessageAt == null) continue;
      if (_activeConversationId == conv.id && _appInForeground) {
        markConversationSeen(conv.id, at: conv.lastMessageAt);
        continue;
      }

      try {
        final messages = await apiClient.getMessages(conv.id);
        if (messages.isEmpty) continue;
        final latest = messages.last;
        if (latest.isOutgoing || latest.id <= (_maxMessageIdByConversation[conv.id] ?? 0)) {
          _maxMessageIdByConversation[conv.id] = latest.id;
          continue;
        }
        _maxMessageIdByConversation[conv.id] = latest.id;
        markConversationUnread(conv.id);
        await _notifyIncoming(
          conversationId: conv.id,
          displayName: conv.displayName,
          preview: latest.body,
          messageId: latest.id,
        );
      } catch (_) {
        // Polling silencioso: no bloquear la lista de chats.
      }
    }
  }

  void seedFromLogin() {
    _seeded = false;
    _notifiedMessageIds.clear();
    _unreadConversationIds.clear();
    _maxMessageIdByConversation.clear();
    _lastMessageAtByConversation.clear();
    _lastSeenAtByConversation.clear();
  }

  Future<void> _seedMaxMessageId(int conversationId) async {
    try {
      final cached =
          await AppServices.messageRepository.getCachedMessages(conversationId);
      if (cached.isEmpty) return;
      final maxId = cached.map((m) => m.id).reduce((a, b) => a > b ? a : b);
      if (maxId > 0) {
        _maxMessageIdByConversation[conversationId] = maxId;
      }
    } catch (_) {}
  }

  Future<void> _notifyIncoming({
    required int conversationId,
    required String displayName,
    required String preview,
    required int messageId,
  }) async {
    if (_notifiedMessageIds.contains(messageId)) return;
    _notifiedMessageIds.add(messageId);

    final showBanner = !_appInForeground ||
        _activeConversationId == null ||
        _activeConversationId != conversationId;

    await HapticFeedback.mediumImpact();

    if (!showBanner) {
      await _playIncomingSound();
      return;
    }

    final body = preview.length > 120 ? '${preview.substring(0, 117)}...' : preview;
    await _notifications.show(
      messageId,
      displayName,
      body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: 'Avisos de mensajes nuevos de clientes',
          importance: Importance.max,
          priority: Priority.high,
          ticker: 'Mensaje nuevo',
          icon: '@mipmap/ic_launcher',
          playSound: true,
          enableVibration: true,
          sound: const RawResourceAndroidNotificationSound('incoming_message'),
          styleInformation: MessagingStyleInformation(
            Person(name: displayName),
            groupConversation: false,
            conversationTitle: displayName,
            messages: [
              Message(
                body,
                DateTime.now(),
                Person(name: displayName),
              ),
            ],
          ),
          category: AndroidNotificationCategory.message,
          visibility: NotificationVisibility.public,
          autoCancel: true,
          onlyAlertOnce: false,
        ),
        iOS: const DarwinNotificationDetails(
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
          interruptionLevel: InterruptionLevel.timeSensitive,
        ),
      ),
      payload: conversationId.toString(),
    );
  }

  Future<void> _playIncomingSound() async {
    try {
      await _player.stop();
      await _player.play(AssetSource(_soundAsset));
    } catch (e) {
      if (kDebugMode) {
        debugPrint('MessageAlertsService: no se pudo reproducir sonido: $e');
      }
    }
  }

  void _onNotificationTap(NotificationResponse response) {
    final payload = response.payload;
    if (payload == null) return;
    final conversationId = int.tryParse(payload);
    if (conversationId == null) return;
    onOpenConversation?.call(conversationId);
  }
}

final messageAlerts = MessageAlertsService.instance;
