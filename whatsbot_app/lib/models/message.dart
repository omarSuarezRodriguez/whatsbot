import 'package:drift/drift.dart' show Value;

import '../data/local/app_database.dart';

class ChatMessage {
  ChatMessage({
    required this.id,
    required this.conversationId,
    required this.direction,
    required this.body,
    required this.waId,
    required this.isAdmin,
    required this.channel,
    required this.status,
    this.deliveredAt,
    this.readAt,
    required this.createdAt,
    this.clientUuid,
  });

  final int id;
  final int conversationId;
  final String direction;
  final String body;
  final String waId;
  final bool isAdmin;
  final String channel;
  final String status;
  final DateTime? deliveredAt;
  final DateTime? readAt;
  final DateTime createdAt;
  final String? clientUuid;

  bool get isOutgoing => direction == 'outgoing' || isAdmin;

  /// Orden cronológico estable (createdAt, luego id).
  static int compareChronological(ChatMessage a, ChatMessage b) {
    final byTime = a.createdAt.compareTo(b.createdAt);
    if (byTime != 0) return byTime;
    return a.id.compareTo(b.id);
  }

  ChatMessage copyWith({
    int? conversationId,
    String? status,
    DateTime? deliveredAt,
    DateTime? readAt,
  }) {
    return ChatMessage(
      id: id,
      conversationId: conversationId ?? this.conversationId,
      direction: direction,
      body: body,
      waId: waId,
      isAdmin: isAdmin,
      channel: channel,
      status: status ?? this.status,
      deliveredAt: deliveredAt ?? this.deliveredAt,
      readAt: readAt ?? this.readAt,
      createdAt: createdAt,
      clientUuid: clientUuid,
    );
  }

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: json['id'] as int,
      conversationId: json['conversation_id'] as int,
      direction: json['direction'] as String,
      body: json['body'] as String,
      waId: json['wa_id'] as String,
      isAdmin: json['is_admin'] as bool? ?? false,
      channel: json['channel'] as String? ?? 'whatsapp',
      status: json['status'] as String? ?? 'delivered',
      deliveredAt: _parseDate(json['delivered_at']),
      readAt: _parseDate(json['read_at']),
      createdAt: DateTime.parse(json['created_at'] as String),
      clientUuid: json['client_id'] as String?,
    );
  }

  factory ChatMessage.fromLocalRow(MessageEntity row) {
    return ChatMessage(
      id: row.id,
      conversationId: row.conversationId,
      direction: row.direction,
      body: row.body,
      waId: row.waId,
      isAdmin: row.isAdmin,
      channel: row.channel,
      status: row.status,
      deliveredAt: row.deliveredAt,
      readAt: row.readAt,
      createdAt: row.createdAt,
      clientUuid: row.clientUuid,
    );
  }

  MessagesCompanion toLocalRow() {
    return MessagesCompanion(
      id: Value(id),
      conversationId: Value(conversationId),
      direction: Value(direction),
      body: Value(body),
      waId: Value(waId),
      isAdmin: Value(isAdmin),
      channel: Value(channel),
      status: Value(status),
      deliveredAt: Value(deliveredAt),
      readAt: Value(readAt),
      createdAt: Value(createdAt),
      clientUuid:
          clientUuid == null ? const Value.absent() : Value(clientUuid),
    );
  }

  static DateTime? _parseDate(dynamic value) {
    if (value == null) return null;
    return DateTime.parse(value as String);
  }
}
