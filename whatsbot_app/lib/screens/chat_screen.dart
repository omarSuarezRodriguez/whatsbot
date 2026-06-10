import 'dart:async' show StreamSubscription, Timer, unawaited;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import '../data/repositories/chat_repository.dart';
import '../data/repositories/message_repository.dart';
import '../di/app_services.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../models/order.dart';
import '../models/realtime_event.dart';
import '../services/api_client.dart';
import '../services/connectivity_service.dart';
import '../services/message_alerts_service.dart';
import '../services/realtime_service.dart';
import '../theme/whatsapp_theme.dart';
import '../widgets/message_bubble.dart';
import '../widgets/typing_indicator.dart';
import 'order_actions_bar.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.conversation,
    this.initialMessages,
  });

  final Conversation conversation;
  final List<ChatMessage>? initialMessages;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();
  PendingOrder? _pendingOrder;
  bool _refreshing = false;
  bool _sending = false;
  bool _orderBusy = false;
  bool _peerTyping = false;
  int _lastMessageCount = 0;
  Timer? _typingStopTimer;
  StreamSubscription<RealtimeEvent>? _realtimeSub;
  StreamSubscription<bool>? _connectivitySub;
  StreamSubscription<bool>? _connectionSub;
  StreamSubscription<List<ChatMessage>>? _messagesSub;
  Timer? _wsFallbackTimer;

  MessageRepository get _messageRepo => AppServices.messageRepository;
  ChatRepository get _chats => AppServices.chatRepository;

  @override
  void initState() {
    super.initState();
    _lastMessageCount = widget.initialMessages?.length ?? 0;
    AppServices.syncEngine.trackOpenConversation(widget.conversation.id);
    messageAlerts.setActiveConversation(widget.conversation.id);
    _inputController.addListener(_onInputChanged);
    _realtimeSub = realtimeService.events.listen(_onRealtimeEvent);
    _connectivitySub = connectivityService.onlineState.listen((online) {
      if (!mounted) return;
      setState(() {});
      if (online) unawaited(AppServices.onAppResumed());
    });
    _connectionSub = realtimeService.connectionState.listen((connected) {
      if (!mounted) return;
      setState(() {});
      _updateWsFallbackTimer(connected);
      if (!connected && connectivityService.isOnline) {
        unawaited(_refresh(silent: true, force: true));
      }
    });
    _updateWsFallbackTimer(realtimeService.isConnected);
    _messagesSub = _messageRepo
        .watchMessages(widget.conversation.id)
        .listen(_onMessagesFromStore);
    SchedulerBinding.instance.scheduleFrameCallback((_) {
      unawaited(_markRead());
      unawaited(_refresh(silent: true));
    });
  }

  @override
  void dispose() {
    AppServices.syncEngine.untrackOpenConversation(widget.conversation.id);
    realtimeService.sendTyping(
      conversationId: widget.conversation.id,
      isTyping: false,
    );
    unawaited(_markConversationSeenOnExit());
    messageAlerts.setActiveConversation(null);
    _inputController.removeListener(_onInputChanged);
    _realtimeSub?.cancel();
    _connectivitySub?.cancel();
    _connectionSub?.cancel();
    _messagesSub?.cancel();
    _wsFallbackTimer?.cancel();
    _typingStopTimer?.cancel();
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  bool _messageBelongsToChat(ChatMessage message) {
    if (message.conversationId == widget.conversation.id) return true;
    return _sameWa(message.waId, widget.conversation.customerWaId);
  }

  void _onMessagesFromStore(List<ChatMessage> messages) {
    if (!mounted) return;

    final count = messages.length;
    final hadGrowth = count > _lastMessageCount;
    _lastMessageCount = count;

    if (messages.isNotEmpty) {
      unawaited(_persistSeen(messages));
    }

    if (hadGrowth && _isNearBottom()) {
      _scrollToBottom(animated: true);
    }

    setState(() {});
  }

  Future<void> _markConversationSeenOnExit() async {
    final messages =
        await _messageRepo.watchMessages(widget.conversation.id).first;
    await _persistSeen(messages);
  }

  Future<void> _persistSeen(List<ChatMessage> messages) async {
    final lastAt = _latestActivityAt(messages);
    if (lastAt == null) return;
    messageAlerts.markConversationSeen(widget.conversation.id, at: lastAt);
    await _chats.markSeen(widget.conversation.id, lastAt);
  }

  DateTime? _latestActivityAt(List<ChatMessage> messages) {
    if (messages.isNotEmpty) {
      return messages
          .map((m) => m.createdAt)
          .reduce((a, b) => a.isAfter(b) ? a : b);
    }
    return widget.conversation.lastMessageAt;
  }

  Future<void> _markRead() async {
    try {
      await apiClient.markConversationRead(widget.conversation.id);
    } catch (_) {}
  }

  void _onInputChanged() {
    if (!realtimeService.isConnected) return;
    final hasText = _inputController.text.trim().isNotEmpty;
    realtimeService.sendTyping(
      conversationId: widget.conversation.id,
      isTyping: hasText,
    );
    _typingStopTimer?.cancel();
    if (hasText) {
      _typingStopTimer = Timer(const Duration(seconds: 2), () {
        realtimeService.sendTyping(
          conversationId: widget.conversation.id,
          isTyping: false,
        );
      });
    }
  }

  Future<void> _onRealtimeEvent(RealtimeEvent event) async {
    if (!mounted) return;

    switch (event.type) {
      case 'message.new':
        final message = event.message;
        if (message == null || !_messageBelongsToChat(message)) break;
        unawaited(_refresh(silent: true, force: true));
        if (!message.isOutgoing) {
          unawaited(_markRead());
        }
        break;
      case 'message.status':
      case 'conversation.updated':
      case 'conversation.sync':
        unawaited(_refresh(silent: true, force: true));
        break;
      case 'order.pending':
        final order = event.order;
        if (order != null &&
            _sameWa(order.waId, widget.conversation.customerWaId)) {
          setState(() => _pendingOrder = order);
        }
        break;
      case 'order.updated':
        final order = event.order;
        if (order == null ||
            !_sameWa(order.waId, widget.conversation.customerWaId)) {
          break;
        }
        setState(() {
          _pendingOrder = order.status == 'pending' ? order : null;
        });
        break;
      case 'typing.start':
        if (event.conversationId == widget.conversation.id) {
          setState(() => _peerTyping = true);
        }
        break;
      case 'typing.stop':
        if (event.conversationId == widget.conversation.id) {
          setState(() => _peerTyping = false);
        }
        break;
    }
  }

  void _updateWsFallbackTimer(bool wsConnected) {
    _wsFallbackTimer?.cancel();
    _wsFallbackTimer = null;
    if (wsConnected || !connectivityService.isOnline) return;
    _wsFallbackTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (!mounted || realtimeService.isConnected) return;
      unawaited(_refresh(silent: true, force: true));
    });
  }

  Future<void> _refresh({bool silent = false, bool force = false}) async {
    if (!connectivityService.isOnline) {
      if (!silent && mounted) setState(() => _refreshing = false);
      return;
    }

    final hasCache = (widget.initialMessages?.isNotEmpty ?? false) ||
        await _messageRepo.hasLocalMessages(widget.conversation.id);
    if (!mounted) return;

    final showLoading = !silent || !hasCache;
    if (showLoading) setState(() => _refreshing = true);

    try {
      await AppServices.syncEngine.syncMessagesIncremental(
        widget.conversation.id,
        force: force || !realtimeService.isConnected,
      );
      if (!silent && _pendingOrder == null) {
        await _loadPendingOrderOnce();
      }
      if (!mounted) return;
      if (showLoading) setState(() => _refreshing = false);
      final allMessages =
          await _messageRepo.watchMessages(widget.conversation.id).first;
      if (allMessages.isNotEmpty) {
        await messageAlerts.handleChatMessages(
          conversationId: widget.conversation.id,
          displayName: widget.conversation.displayName,
          messages: allMessages,
        );
      }
    } catch (_) {
      if (!mounted) return;
      if (showLoading) setState(() => _refreshing = false);
    }
  }

  Future<void> _loadPendingOrderOnce() async {
    final orders = await apiClient.getPendingOrders();
    final wa = widget.conversation.customerWaId;
    for (final o in orders) {
      if (_sameWa(o.waId, wa)) {
        _pendingOrder = o;
        return;
      }
    }
  }

  bool _sameWa(String a, String b) {
    final na = a.replaceAll(RegExp(r'[^0-9+]'), '');
    final nb = b.replaceAll(RegExp(r'[^0-9+]'), '');
    return na == nb || na.endsWith(nb) || nb.endsWith(na);
  }

  bool _isNearBottom() {
    if (!_scrollController.hasClients) return true;
    return _scrollController.offset <= 96;
  }

  void _scrollToBottom({bool force = true, bool animated = true}) {
    if (!force && !_isNearBottom()) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      if (!animated) {
        _scrollController.jumpTo(0);
        return;
      }
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _send() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _sending) return;

    _inputController.clear();
    setState(() => _sending = true);
    realtimeService.sendTyping(
      conversationId: widget.conversation.id,
      isTyping: false,
    );
    try {
      final result = await _messageRepo.sendMessage(
        conversationId: widget.conversation.id,
        customerWaId: widget.conversation.customerWaId,
        body: text,
      );
      if (!mounted) return;
      _scrollToBottom(force: true);
      if (result.queued) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Sin conexión. El mensaje se enviará automáticamente.'),
            duration: Duration(seconds: 3),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _approveOrder() async {
    final order = _pendingOrder;
    if (order == null || _orderBusy) return;
    setState(() => _orderBusy = true);
    try {
      final msg = await apiClient.approveOrder(order.orderId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      setState(() => _pendingOrder = null);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    } finally {
      if (mounted) setState(() => _orderBusy = false);
    }
  }

  Future<void> _rejectOrder() async {
    final order = _pendingOrder;
    if (order == null || _orderBusy) return;
    setState(() => _orderBusy = true);
    try {
      final msg = await apiClient.rejectOrder(order.orderId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      setState(() => _pendingOrder = null);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    } finally {
      if (mounted) setState(() => _orderBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final typingOffset = _peerTyping ? 1 : 0;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.conversation.displayName),
            Text(
              _peerTyping
                  ? 'escribiendo…'
                  : widget.conversation.customerWaId,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.normal,
                fontStyle: _peerTyping ? FontStyle.italic : FontStyle.normal,
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          if (_pendingOrder != null)
            OrderActionsBar(
              order: _pendingOrder!,
              busy: _orderBusy,
              onApprove: _approveOrder,
              onReject: _rejectOrder,
            ),
          Expanded(
            child: Container(
              color: WhatsAppTheme.chatBackground,
              child: StreamBuilder<List<ChatMessage>>(
                stream: _messageRepo.watchMessages(widget.conversation.id),
                initialData: widget.initialMessages ?? const [],
                builder: (context, snapshot) {
                  final messages = snapshot.data ?? const [];
                  final showSpinner = messages.isEmpty && _refreshing;

                  if (showSpinner) {
                    return const Center(child: CircularProgressIndicator());
                  }

                  return ListView.builder(
                    controller: _scrollController,
                    reverse: true,
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    itemCount: messages.length + typingOffset,
                    itemBuilder: (_, i) {
                      if (_peerTyping && i == 0) {
                        return const TypingIndicator();
                      }
                      final messageIndex =
                          messages.length - 1 - (i - typingOffset);
                      final message = messages[messageIndex];
                      return MessageBubble(
                        key: ValueKey(
                          message.clientUuid ?? 'msg-${message.id}',
                        ),
                        message: message,
                      );
                    },
                  );
                },
              ),
            ),
          ),
          Material(
            color: const Color(0xFFF0F0F0),
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(8, 6, 8, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _inputController,
                        decoration: InputDecoration(
                          hintText: 'Mensaje',
                          filled: true,
                          fillColor: Colors.white,
                          contentPadding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 10,
                          ),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(24),
                            borderSide: BorderSide.none,
                          ),
                        ),
                        textInputAction: TextInputAction.send,
                        textCapitalization: TextCapitalization.sentences,
                        onSubmitted: (_) => _send(),
                        maxLines: 4,
                        minLines: 1,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Material(
                      color: WhatsAppTheme.accentGreen,
                      shape: const CircleBorder(),
                      child: InkWell(
                        customBorder: const CircleBorder(),
                        onTap: _sending ? null : _send,
                        child: SizedBox(
                          width: 48,
                          height: 48,
                          child: _sending
                              ? const Padding(
                                  padding: EdgeInsets.all(12),
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Icon(Icons.send, color: Colors.white),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
