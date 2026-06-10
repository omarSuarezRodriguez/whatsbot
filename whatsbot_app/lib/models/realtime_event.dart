import 'conversation.dart';
import 'message.dart';
import 'order.dart';

/// Evento JSON del WebSocket `/whatsbot/ws`.
class RealtimeEvent {
  RealtimeEvent({
    required this.type,
    this.message,
    this.conversation,
    this.order,
    this.messageId,
    this.conversationId,
    this.status,
    this.deliveredAt,
    this.readAt,
  });

  final String type;
  final ChatMessage? message;
  final Conversation? conversation;
  final PendingOrder? order;
  final int? messageId;
  final int? conversationId;
  final String? status;
  final DateTime? deliveredAt;
  final DateTime? readAt;

  factory RealtimeEvent.fromJson(Map<String, dynamic> json) {
    final msg = json['message'];
    final conv = json['conversation'];
    final ord = json['order'];
    return RealtimeEvent(
      type: json['type'] as String? ?? 'unknown',
      message: msg is Map<String, dynamic>
          ? ChatMessage.fromJson(msg)
          : null,
      conversation: conv is Map<String, dynamic>
          ? Conversation.fromJson(conv)
          : null,
      order: ord is Map<String, dynamic>
          ? PendingOrder.fromJson(ord)
          : null,
      messageId: _asInt(json['message_id']),
      conversationId: _asInt(json['conversation_id']),
      status: json['status'] as String?,
      deliveredAt: _parseDate(json['delivered_at']),
      readAt: _parseDate(json['read_at']),
    );
  }

  static DateTime? _parseDate(dynamic value) {
    if (value == null) return null;
    return DateTime.parse(value as String);
  }

  static int? _asInt(dynamic value) {
    if (value is int) return value;
    if (value is String) return int.tryParse(value);
    return null;
  }
}
