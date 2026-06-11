import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/models/message.dart';

void main() {
  ChatMessage msg({
    required int id,
    required DateTime createdAt,
    String? clientUuid,
  }) {
    return ChatMessage(
      id: id,
      conversationId: 1,
      direction: 'incoming',
      body: 'Hola',
      waId: '+5491111111111',
      isAdmin: false,
      channel: 'whatsapp',
      status: 'delivered',
      createdAt: createdAt,
      clientUuid: clientUuid,
    );
  }

  test('compareChronological ordena por createdAt y desempata por id', () {
    final early = msg(id: 10, createdAt: DateTime.utc(2026, 6, 5, 10, 28));
    final late = msg(id: 11, createdAt: DateTime.utc(2026, 6, 5, 10, 30));
    final tieFirst = msg(id: 5, createdAt: DateTime.utc(2026, 6, 5, 10, 29));
    final tieSecond = msg(id: 8, createdAt: DateTime.utc(2026, 6, 5, 10, 29));

    final sorted = [late, tieSecond, early, tieFirst]
      ..sort(ChatMessage.compareChronological);

    expect(sorted.map((m) => m.id).toList(), [10, 5, 8, 11]);
  });

  test('fromJson normaliza createdAt a UTC', () {
    final parsed = ChatMessage.fromJson({
      'id': 1,
      'conversation_id': 1,
      'direction': 'outgoing',
      'body': 'Admin',
      'wa_id': '+5491111111111',
      'is_admin': true,
      'created_at': '2026-06-05T10:30:00Z',
    });

    expect(parsed.createdAt.isUtc, isTrue);
    expect(parsed.createdAt, DateTime.utc(2026, 6, 5, 10, 30));
  });
}
