import 'dart:async' show StreamSubscription, unawaited;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/repositories/chat_repository.dart';
import '../di/app_services.dart';
import '../models/conversation.dart';
import '../models/realtime_event.dart';
import '../main.dart';
import '../services/api_client.dart';
import '../services/connectivity_service.dart';
import '../services/message_alerts_service.dart';
import '../services/realtime_service.dart';
import '../theme/whatsapp_theme.dart';
import 'chat_screen.dart';
import 'settings_screen.dart';

class ChatsListScreen extends StatefulWidget {
  const ChatsListScreen({super.key});

  @override
  State<ChatsListScreen> createState() => _ChatsListScreenState();
}

class _ChatsListScreenState extends State<ChatsListScreen> {
  bool _refreshing = false;
  String? _error;
  StreamSubscription<RealtimeEvent>? _realtimeSub;
  StreamSubscription<bool>? _connectionSub;
  StreamSubscription<bool>? _connectivitySub;
  bool _wasConnected = false;

  ChatRepository get _chats => AppServices.chatRepository;

  @override
  void initState() {
    super.initState();
    messageAlerts.onOpenConversation = _openConversationById;
    _wasConnected = realtimeService.isConnected;
    unawaited(realtimeService.ensureConnected());
    _realtimeSub = realtimeService.events.listen(_onRealtimeEvent);
    _connectionSub = realtimeService.connectionState.listen((connected) {
      if (mounted) setState(() {});
      if (connected && !_wasConnected) {
        unawaited(_refresh(silent: true));
      }
      _wasConnected = connected;
    });
    _connectivitySub = connectivityService.onlineState.listen((online) {
      if (mounted) setState(() {});
      if (online) unawaited(AppServices.onAppResumed());
    });
    unawaited(_refresh(silent: true));
  }

  @override
  void dispose() {
    messageAlerts.onOpenConversation = null;
    _realtimeSub?.cancel();
    _connectionSub?.cancel();
    _connectivitySub?.cancel();
    super.dispose();
  }

  bool get _showOfflineIcon =>
      !connectivityService.isOnline || !realtimeService.isConnected;

  Future<void> _onRealtimeEvent(RealtimeEvent event) async {
    if (!mounted) return;

    switch (event.type) {
      case 'message.new':
        final message = event.message;
        if (message == null) break;

        final resolved =
            await AppServices.messageRepository.resolveForLocalStore(message);
        final chat = await _chats.getConversation(resolved.conversationId) ??
            await _chats.findConversationByWaId(resolved.waId);
        if (chat != null) {
          await _chats.bumpConversationFromMessage(chat, resolved);
          if (!resolved.isOutgoing) {
            await messageAlerts.handleRealtimeMessage(
              conversation: chat,
              message: resolved,
            );
          }
        }
        break;
      case 'conversation.updated':
      case 'conversation.sync':
        final conversation = event.conversation;
        if (conversation != null) {
          await _chats.upsertConversationFromServer(conversation);
        }
        break;
      default:
        break;
    }
    if (mounted) setState(() {});
  }

  Future<void> _openChat(Conversation chat) async {
    messageAlerts.markConversationSeen(
      chat.id,
      at: chat.lastMessageAt ?? DateTime.now(),
    );
    final initial =
        await AppServices.messageRepository.getCachedMessages(chat.id);
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ChatScreen(
          conversation: chat,
          initialMessages: initial,
        ),
      ),
    );
    if (mounted) unawaited(_refresh(silent: true));
  }

  Future<void> _openConversationById(int conversationId) async {
    Conversation? chat = await _chats.getConversation(conversationId);
    if (chat == null) {
      await _refresh(silent: true);
      chat = await _chats.getConversation(conversationId);
    }
    if (chat == null || !mounted) return;

    messageAlerts.markConversationSeen(
      chat.id,
      at: chat.lastMessageAt ?? DateTime.now(),
    );

    final nav = navigatorKey.currentState;
    if (nav == null) return;
    final initial =
        await AppServices.messageRepository.getCachedMessages(chat.id);
    if (!mounted) return;
    await nav.push(
      MaterialPageRoute(
        builder: (_) => ChatScreen(
          conversation: chat!,
          initialMessages: initial,
        ),
      ),
    );
    if (mounted) unawaited(_refresh(silent: true));
  }

  Future<void> _refresh({bool silent = false}) async {
    if (!connectivityService.isOnline) {
      if (!silent && mounted) {
        setState(() {
          _refreshing = false;
          _error = 'Sin conexión. Los chats guardados siguen disponibles.';
        });
      }
      return;
    }

    if (!silent) {
      setState(() {
        _refreshing = true;
        _error = null;
      });
    }
    try {
      final list = await AppServices.syncEngine.syncConversationsIncremental();
      if (!mounted) return;
      setState(() {
        _refreshing = false;
        _error = null;
      });
      await messageAlerts.handleConversations(list);
      if (mounted) setState(() {});
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        if (!silent) _error = e.message;
        _refreshing = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        if (!silent) _error = 'Sin conexión con la API';
        _refreshing = false;
      });
    }
  }

  String _formatTime(DateTime? dt) {
    if (dt == null) return '';
    final local = dt.toLocal();
    final now = DateTime.now();
    if (local.year == now.year &&
        local.month == now.month &&
        local.day == now.day) {
      return DateFormat('HH:mm').format(local);
    }
    return DateFormat('dd/MM').format(local);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(apiClient.businessName ?? 'WhatsBot'),
        actions: [
          if (_showOfflineIcon)
            const Padding(
              padding: EdgeInsets.only(right: 4),
              child: Icon(
                Icons.cloud_off,
                size: 20,
                color: Colors.white70,
              ),
            ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Ajustes',
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              );
              if (mounted) unawaited(_refresh(silent: true));
            },
          ),
        ],
      ),
      body: StreamBuilder<List<Conversation>>(
        stream: _chats.watchConversations(),
        builder: (context, snapshot) {
          final conversations = snapshot.data ?? [];
          final showSpinner = conversations.isEmpty && _refreshing;
          final showError = conversations.isEmpty && _error != null;

          if (showSpinner) {
            return const Center(child: CircularProgressIndicator());
          }
          if (showError) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(_error!),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: () => _refresh(),
                    child: const Text('Reintentar'),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () => _refresh(),
            child: conversations.isEmpty
                ? ListView(
                    children: const [
                      SizedBox(height: 120),
                      Center(
                        child: Text(
                          'Aún no hay conversaciones.\n'
                          'Cuando un cliente escriba al bot, aparecerá aquí.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: WhatsAppTheme.subtitleGrey),
                        ),
                      ),
                    ],
                  )
                : ListView.separated(
                    itemCount: conversations.length,
                    separatorBuilder: (context, index) => const Divider(
                      height: 1,
                      indent: 72,
                    ),
                    itemBuilder: (context, index) {
                      final chat = conversations[index];
                      final unread =
                          messageAlerts.isConversationUnread(chat);
                      return ListTile(
                        leading: CircleAvatar(
                          backgroundColor: WhatsAppTheme.accentGreen,
                          child: Text(
                            chat.displayName.isNotEmpty
                                ? chat.displayName[0].toUpperCase()
                                : '?',
                            style: const TextStyle(color: Colors.white),
                          ),
                        ),
                        title: Text(
                          chat.displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontWeight:
                                unread ? FontWeight.w700 : FontWeight.w500,
                          ),
                        ),
                        subtitle: Text(
                          chat.lastMessagePreview ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: unread
                                ? Colors.black87
                                : WhatsAppTheme.subtitleGrey,
                            fontWeight:
                                unread ? FontWeight.w600 : FontWeight.normal,
                          ),
                        ),
                        trailing: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              _formatTime(chat.lastMessageAt),
                              style: TextStyle(
                                fontSize: 12,
                                color: unread
                                    ? WhatsAppTheme.accentGreen
                                    : WhatsAppTheme.subtitleGrey,
                                fontWeight:
                                    unread ? FontWeight.w600 : FontWeight.normal,
                              ),
                            ),
                            if (unread) ...[
                              const SizedBox(height: 6),
                              Container(
                                width: 10,
                                height: 10,
                                decoration: const BoxDecoration(
                                  color: WhatsAppTheme.accentGreen,
                                  shape: BoxShape.circle,
                                ),
                              ),
                            ],
                          ],
                        ),
                        onTap: () => unawaited(_openChat(chat)),
                      );
                    },
                  ),
          );
        },
      ),
    );
  }
}
