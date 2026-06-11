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
  List<ChatMessage> _displayMessages = [];
  late final Stream<List<ChatMessage>> _messagesStream;
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
    _messagesStream = _messageRepo.watchMessages(widget.conversation.id);
    _displayMessages = List<ChatMessage>.from(widget.initialMessages ?? []);
    if (_displayMessages.isNotEmpty) {
      _displayMessages.sort(ChatMessage.compareChronological);
    }
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
    _messagesSub = _messagesStream.listen(_onMessagesFromStore);
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

  void _onMessagesFromStore(List<ChatMessage> storeMessages) {
    _applyStoreSnapshot(storeMessages);
  }

  void _applyStoreSnapshot(
    List<ChatMessage> storeMessages, {
    bool scrollIfNearBottom = true,
  }) {
    if (!mounted) return;

    final previousCount = _displayMessages.length;
    final prevLastId =
        _displayMessages.isNotEmpty ? _displayMessages.last.id : null;
    final next = _reconcileWithStore(storeMessages);
    final changed = _messagesSnapshotChanged(_displayMessages, next);
    _displayMessages = next;

    final hadGrowth = _displayMessages.length > previousCount ||
        (_displayMessages.isNotEmpty && _displayMessages.last.id != prevLastId);

    if (_displayMessages.isNotEmpty) {
      unawaited(_persistSeen(_displayMessages));
    }

    if (scrollIfNearBottom && hadGrowth && _isNearBottom()) {
      _scrollToBottom(animated: true);
    }

    if (changed) setState(() {});
  }

  Future<void> _reloadDisplayFromStore({bool scrollIfNearBottom = false}) async {
    if (!mounted) return;
    final store =
        await _messageRepo.watchMessages(widget.conversation.id).first;
    if (!mounted) return;
    _applyStoreSnapshot(store, scrollIfNearBottom: scrollIfNearBottom);
  }

  bool _messagesSnapshotChanged(
    List<ChatMessage> before,
    List<ChatMessage> after,
  ) {
    if (before.length != after.length) return true;
    for (var i = 0; i < before.length; i++) {
      final a = before[i];
      final b = after[i];
      if (a.id != b.id ||
          a.status != b.status ||
          a.body != b.body ||
          a.deliveredAt != b.deliveredAt ||
          a.readAt != b.readAt) {
        return true;
      }
    }
    return false;
  }

  List<ChatMessage> _reconcileWithStore(List<ChatMessage> store) {
    final storeIds = {for (final m in store) m.id};
    final storeByClientUuid = <String, ChatMessage>{
      for (final m in store)
        if (m.clientUuid != null && m.clientUuid!.isNotEmpty) m.clientUuid!: m,
    };

    final merged = List<ChatMessage>.from(store);
    for (final message in _displayMessages) {
      if (storeIds.contains(message.id)) continue;
      if (message.clientUuid != null &&
          message.clientUuid!.isNotEmpty &&
          storeByClientUuid.containsKey(message.clientUuid!)) {
        continue;
      }
      if (_messageBelongsToChat(message)) {
        merged.add(message);
      }
    }

    merged.sort(ChatMessage.compareChronological);
    return merged;
  }

  bool _mergeMessageIntoDisplay(ChatMessage incoming) {
    final local = incoming.copyWith(conversationId: widget.conversation.id);

    if (incoming.clientUuid != null && incoming.clientUuid!.isNotEmpty) {
      final idx = _displayMessages.indexWhere(
        (m) => m.clientUuid == incoming.clientUuid,
      );
      if (idx >= 0) {
        final wasPending = _displayMessages[idx].status == 'pending';
        _displayMessages[idx] =
            _mergeMessageFields(_displayMessages[idx], local);
        _sortDisplayMessages();
        return wasPending || _displayMessages[idx].id != incoming.id;
      }
    }

    final byId = _displayMessages.indexWhere((m) => m.id == incoming.id);
    if (byId >= 0) {
      _displayMessages[byId] =
          _mergeMessageFields(_displayMessages[byId], local);
      _sortDisplayMessages();
      return false;
    }

    _displayMessages.add(local);
    _sortDisplayMessages();
    return true;
  }

  ChatMessage _mergeMessageFields(ChatMessage existing, ChatMessage incoming) {
    return ChatMessage(
      id: incoming.id,
      conversationId: widget.conversation.id,
      direction: incoming.direction,
      body: incoming.body,
      waId: incoming.waId,
      isAdmin: incoming.isAdmin,
      channel: incoming.channel,
      status: incoming.status,
      deliveredAt: incoming.deliveredAt ?? existing.deliveredAt,
      readAt: incoming.readAt ?? existing.readAt,
      createdAt: incoming.createdAt,
      clientUuid: incoming.clientUuid ?? existing.clientUuid,
    );
  }

  void _applyStatusUpdate(RealtimeEvent event) {
    final messageId = event.messageId;
    if (messageId == null) return;

    final idx = _displayMessages.indexWhere((m) => m.id == messageId);
    if (idx < 0) return;

    _displayMessages[idx] = _displayMessages[idx].copyWith(
      status: event.status ?? _displayMessages[idx].status,
      deliveredAt: event.deliveredAt ?? _displayMessages[idx].deliveredAt,
      readAt: event.readAt ?? _displayMessages[idx].readAt,
    );
  }

  void _sortDisplayMessages() {
    _displayMessages.sort(ChatMessage.compareChronological);
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
        if (message == null) break;
        final resolved = await _messageRepo.resolveForLocalStore(message);
        if (!_messageBelongsToChat(resolved)) break;
        final hadGrowth = _mergeMessageIntoDisplay(resolved);
        setState(() {});
        if (hadGrowth && _isNearBottom()) {
          _scrollToBottom(animated: true);
        }
        unawaited(_refresh(silent: true, force: true));
        if (!message.isOutgoing) {
          unawaited(_markRead());
        }
        break;
      case 'message.status':
        _applyStatusUpdate(event);
        setState(() {});
        unawaited(_refresh(silent: true, force: true));
        break;
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
      await _reloadDisplayFromStore(scrollIfNearBottom: true);
      if (!mounted) return;
      if (_displayMessages.isNotEmpty) {
        await messageAlerts.handleChatMessages(
          conversationId: widget.conversation.id,
          displayName: widget.conversation.displayName,
          messages: _displayMessages,
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

  String _waDigits(String wa) => wa.replaceAll(RegExp(r'\D'), '');

  bool _sameWa(String a, String b) {
    final da = _waDigits(a);
    final db = _waDigits(b);
    if (da.isEmpty || db.isEmpty) return false;
    return da == db || da.endsWith(db) || db.endsWith(da);
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
      await _reloadDisplayFromStore(scrollIfNearBottom: true);
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
              child: _displayMessages.isEmpty && _refreshing
                  ? const Center(child: CircularProgressIndicator())
                  : ListView.builder(
                      controller: _scrollController,
                      reverse: true,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      itemCount: _displayMessages.length + typingOffset,
                      itemBuilder: (_, i) {
                        if (_peerTyping && i == 0) {
                          return const TypingIndicator();
                        }
                        final messageIndex = _displayMessages.length -
                            1 -
                            (i - typingOffset);
                        final message = _displayMessages[messageIndex];
                        return MessageBubble(
                          key: ValueKey(
                            message.clientUuid ?? 'msg-${message.id}',
                          ),
                          message: message,
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
