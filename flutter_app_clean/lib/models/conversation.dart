import 'package:drift/drift.dart' show Value;

import '../data/local/app_database.dart';

class Conversation {
  Conversation({
    required this.id,
    required this.businessId,
    required this.customerWaId,
    this.customerName,
    this.lastMessagePreview,
    this.lastMessageAt,
    required this.updatedAt,
    this.lastSeenAt,
  });

  final int id;
  final String businessId;
  final String customerWaId;
  final String? customerName;
  final String? lastMessagePreview;
  final DateTime? lastMessageAt;
  final DateTime updatedAt;
  final DateTime? lastSeenAt;

  String get displayName =>
      (customerName != null && customerName!.trim().isNotEmpty)
          ? customerName!
          : customerWaId;

  Conversation copyWith({
    String? customerName,
    String? lastMessagePreview,
    DateTime? lastMessageAt,
    DateTime? updatedAt,
    DateTime? lastSeenAt,
  }) {
    return Conversation(
      id: id,
      businessId: businessId,
      customerWaId: customerWaId,
      customerName: customerName ?? this.customerName,
      lastMessagePreview: lastMessagePreview ?? this.lastMessagePreview,
      lastMessageAt: lastMessageAt ?? this.lastMessageAt,
      updatedAt: updatedAt ?? this.updatedAt,
      lastSeenAt: lastSeenAt ?? this.lastSeenAt,
    );
  }

  factory Conversation.fromJson(Map<String, dynamic> json) {
    return Conversation(
      id: json['id'] as int,
      businessId: json['business_id'] as String,
      customerWaId: json['customer_wa_id'] as String,
      customerName: json['customer_name'] as String?,
      lastMessagePreview: json['last_message_preview'] as String?,
      lastMessageAt: _parseDate(json['last_message_at']),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  factory Conversation.fromLocalRow(ConversationEntity row) {
    return Conversation(
      id: row.id,
      businessId: row.businessId,
      customerWaId: row.customerWaId,
      customerName: row.customerName,
      lastMessagePreview: row.lastMessagePreview,
      lastMessageAt: row.lastMessageAt,
      updatedAt: row.updatedAt,
      lastSeenAt: row.lastSeenAt,
    );
  }

  ConversationsCompanion toLocalRow({DateTime? lastSeenAtOverride}) {
    final now = DateTime.now().toUtc();
    return ConversationsCompanion(
      id: Value(id),
      businessId: Value(businessId),
      customerWaId: Value(customerWaId),
      customerName: Value(customerName),
      lastMessagePreview: Value(lastMessagePreview),
      lastMessageAt: Value(lastMessageAt),
      updatedAt: Value(updatedAt),
      lastSeenAt: lastSeenAtOverride != null
          ? Value(lastSeenAtOverride)
          : (lastSeenAt == null
              ? const Value.absent()
              : Value(lastSeenAt)),
      syncedAt: Value(now),
    );
  }

  static DateTime? _parseDate(dynamic value) {
    if (value == null) return null;
    return DateTime.parse(value as String);
  }
}
