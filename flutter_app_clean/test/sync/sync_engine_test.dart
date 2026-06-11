import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/data/local/app_database.dart';
import 'package:whatsbot_app/data/repositories/chat_repository.dart';
import 'package:whatsbot_app/data/repositories/message_repository.dart';
import 'package:whatsbot_app/data/sync/sync_engine.dart';
import 'package:whatsbot_app/models/conversation.dart';
import 'package:whatsbot_app/models/message.dart';
import 'package:whatsbot_app/models/realtime_event.dart';
import 'package:whatsbot_app/services/realtime_service.dart';

import '../helpers/test_api_client.dart';

void main() {
  late AppDatabase db;
  late TestApiClient testApi;
  late ChatRepository chats;
  late MessageRepository messages;
  late SyncEngine engine;

  setUp(() async {
    db = AppDatabase.forTesting(NativeDatabase.memory());
    testApi = TestApiClient();
    await testApi.login();
    chats = ChatRepository(db, testApi.client);
    messages = MessageRepository(db, testApi.client);
    engine = SyncEngine(chats, messages);

    await chats.upsertConversation(
      Conversation(
        id: 1,
        businessId: 'default',
        customerWaId: '+5491111111111',
        updatedAt: DateTime.utc(2026, 6, 1, 10),
      ),
    );
  });

  tearDown(() async {
    await db.close();
  });

  test('handleRealtimeEvent persiste message.new en SQLite', () async {
    final event = RealtimeEvent(
      type: 'message.new',
      message: ChatMessage(
        id: 77,
        conversationId: 1,
        direction: 'incoming',
        body: 'Desde WS',
        waId: '+5491111111111',
        isAdmin: false,
        channel: 'whatsapp',
        status: 'delivered',
        createdAt: DateTime.utc(2026, 6, 1, 12),
      ),
      conversation: Conversation(
        id: 1,
        businessId: 'default',
        customerWaId: '+5491111111111',
        lastMessagePreview: 'Desde WS',
        lastMessageAt: DateTime.utc(2026, 6, 1, 12),
        updatedAt: DateTime.utc(2026, 6, 1, 12),
      ),
    );

    await engine.handleRealtimeEvent(event);

    final stored = await messages.watchMessages(1).first;
    expect(stored.single.id, 77);
    expect(stored.single.body, 'Desde WS');

    final conversation = await chats.getConversation(1);
    expect(conversation?.lastMessagePreview, 'Desde WS');
  });

  test('handleRealtimeEvent sube conversación aunque no exista en SQLite', () async {
    final message = ChatMessage(
      id: 91,
      conversationId: 42,
      direction: 'incoming',
      body: 'Primer mensaje local',
      waId: '+5491111111999',
      isAdmin: false,
      channel: 'whatsapp',
      status: 'delivered',
      createdAt: DateTime.utc(2026, 6, 1, 16),
    );

    testApi.conversations
      ..clear()
      ..add({
        'id': 42,
        'business_id': 'default',
        'customer_wa_id': '+5491111111999',
        'customer_name': 'Cliente nuevo',
        'last_message_preview': 'Primer mensaje local',
        'last_message_at': '2026-06-01T16:00:00Z',
        'updated_at': '2026-06-01T16:00:00Z',
      });

    await engine.handleRealtimeEvent(
      RealtimeEvent(
        type: 'message.new',
        message: message,
      ),
    );

    final conversation = await chats.getConversation(42);
    expect(conversation?.lastMessagePreview, 'Primer mensaje local');
    expect(conversation?.lastMessageAt?.toUtc(), DateTime.utc(2026, 6, 1, 16));
  });

  test('handleRealtimeEvent actualiza conversación aunque el mensaje esté deduplicado',
      () async {
    final message = ChatMessage(
      id: 88,
      conversationId: 1,
      direction: 'incoming',
      body: 'Cliente escribe',
      waId: '+5491111111111',
      isAdmin: false,
      channel: 'whatsapp',
      status: 'delivered',
      createdAt: DateTime.utc(2026, 6, 1, 15),
    );
    await messages.upsertMessage(message);

    await chats.upsertConversation(
      Conversation(
        id: 1,
        businessId: 'default',
        customerWaId: '+5491111111111',
        lastMessagePreview: 'Viejo',
        lastMessageAt: DateTime.utc(2026, 6, 1, 10),
        updatedAt: DateTime.utc(2026, 6, 1, 10),
      ),
    );

    await engine.handleRealtimeEvent(
      RealtimeEvent(
        type: 'message.new',
        message: message,
        conversation: Conversation(
          id: 1,
          businessId: 'default',
          customerWaId: '+5491111111111',
          lastMessagePreview: 'Cliente escribe',
          lastMessageAt: DateTime.utc(2026, 6, 1, 15),
          updatedAt: DateTime.utc(2026, 6, 1, 15),
        ),
      ),
    );

    final conversation = await chats.getConversation(1);
    expect(conversation?.lastMessageAt?.toUtc(), DateTime.utc(2026, 6, 1, 15));
    expect(conversation?.lastMessagePreview, 'Cliente escribe');
  });

  test('syncMessagesIncremental omite sync si caché reciente y WS conectado', () async {
    realtimeService.debugSetConnected(true);
    testApi.messagesByConversation[1] = [
      {
        'id': 10,
        'conversation_id': 1,
        'direction': 'incoming',
        'body': 'Cacheado',
        'wa_id': '+5491111111111',
        'is_admin': false,
        'channel': 'whatsapp',
        'status': 'delivered',
        'created_at': DateTime.utc(2026, 6, 1, 11).toIso8601String(),
      },
    ];
    await messages.refreshFromApi(1, incremental: true);
    testApi.messagesByConversation[1] = [
      {
        'id': 11,
        'conversation_id': 1,
        'direction': 'incoming',
        'body': 'Nuevo',
        'wa_id': '+5491111111111',
        'is_admin': false,
        'channel': 'whatsapp',
        'status': 'delivered',
        'created_at': DateTime.utc(2026, 6, 1, 12).toIso8601String(),
      },
    ];

    final skipped = await engine.syncMessagesIncremental(1);
    expect(skipped, isEmpty);

    final stored = await messages.watchMessages(1).first;
    expect(stored, hasLength(1));
    expect(stored.single.id, 10);
  });

  test('handleRealtimeEvent guarda message.new en hilo local por wa_id', () async {
    await chats.upsertConversation(
      Conversation(
        id: 1,
        businessId: 'default',
        customerWaId: '+5491111111111',
        lastMessagePreview: 'Viejo',
        lastMessageAt: DateTime.utc(2026, 6, 1, 10),
        updatedAt: DateTime.utc(2026, 6, 1, 10),
      ),
    );
    await chats.upsertConversation(
      Conversation(
        id: 99,
        businessId: 'default',
        customerWaId: '+5498888888888',
        updatedAt: DateTime.utc(2026, 6, 1, 9),
      ),
    );

    await engine.handleRealtimeEvent(
      RealtimeEvent(
        type: 'message.new',
        message: ChatMessage(
          id: 120,
          conversationId: 99,
          direction: 'incoming',
          body: 'En hilo correcto',
          waId: '+5491111111111',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: DateTime.utc(2026, 6, 5, 16),
        ),
      ),
    );

    final stored = await messages.watchMessages(1).first;
    expect(stored.single.id, 120);
    expect(stored.single.body, 'En hilo correcto');

    final conversation = await chats.getConversation(1);
    expect(conversation?.lastMessagePreview, 'En hilo correcto');
    expect(conversation?.lastMessageAt?.toUtc(), DateTime.utc(2026, 6, 5, 16));
  });

  test('syncMessagesIncremental con caché reciente y WS caído no omite sync', () async {
    realtimeService.debugSetConnected(false);
    testApi.messagesByConversation[1] = [
      {
        'id': 10,
        'conversation_id': 1,
        'direction': 'incoming',
        'body': 'Cacheado',
        'wa_id': '+5491111111111',
        'is_admin': false,
        'channel': 'whatsapp',
        'status': 'delivered',
        'created_at': DateTime.utc(2026, 6, 1, 11).toIso8601String(),
      },
    ];
    await messages.refreshFromApi(1, incremental: true);
    testApi.messagesByConversation[1] = [
      {
        'id': 10,
        'conversation_id': 1,
        'direction': 'incoming',
        'body': 'Cacheado',
        'wa_id': '+5491111111111',
        'is_admin': false,
        'channel': 'whatsapp',
        'status': 'delivered',
        'created_at': DateTime.utc(2026, 6, 1, 11).toIso8601String(),
      },
      {
        'id': 11,
        'conversation_id': 1,
        'direction': 'incoming',
        'body': 'Nuevo con WS caído',
        'wa_id': '+5491111111111',
        'is_admin': false,
        'channel': 'whatsapp',
        'status': 'delivered',
        'created_at': DateTime.utc(2026, 6, 1, 12).toIso8601String(),
      },
    ];

    final synced = await engine.syncMessagesIncremental(1);
    expect(synced, isNotEmpty);

    final stored = await messages.watchMessages(1).first;
    expect(stored, hasLength(2));
    expect(
      stored.any((m) => m.id == 11 && m.body == 'Nuevo con WS caído'),
      isTrue,
    );
  });

  test('handleRealtimeEvent dispara onIncomingMessage para entrantes', () async {
    Conversation? notifiedConv;
    ChatMessage? notifiedMsg;
    engine.onIncomingMessage = (conv, msg) async {
      notifiedConv = conv;
      notifiedMsg = msg;
    };

    final event = RealtimeEvent(
      type: 'message.new',
      message: ChatMessage(
        id: 88,
        conversationId: 1,
        direction: 'incoming',
        body: 'Alerta entrante',
        waId: '+5491111111111',
        isAdmin: false,
        channel: 'whatsapp',
        status: 'delivered',
        createdAt: DateTime.utc(2026, 6, 5, 15),
      ),
    );

    await engine.handleRealtimeEvent(event);

    expect(notifiedConv?.id, 1);
    expect(notifiedMsg?.id, 88);
    expect(notifiedMsg?.body, 'Alerta entrante');
  });

  test('handleRealtimeEvent no dispara onIncomingMessage para salientes', () async {
    var called = false;
    engine.onIncomingMessage = (_, _) async {
      called = true;
    };

    await engine.handleRealtimeEvent(
      RealtimeEvent(
        type: 'message.new',
        message: ChatMessage(
          id: 89,
          conversationId: 1,
          direction: 'outgoing',
          body: 'Admin',
          waId: '+5491111111111',
          isAdmin: true,
          channel: 'whatsapp',
          status: 'sent',
          createdAt: DateTime.utc(2026, 6, 5, 15),
        ),
      ),
    );

    expect(called, isFalse);
  });

  test('syncOnReconnect vacía cola saliente pendiente', () async {
    testApi.failSend = true;
    await messages.sendMessage(
      conversationId: 1,
      customerWaId: '+5491111111111',
      body: 'Cola',
    );

    testApi.failSend = false;
    engine.trackOpenConversation(1);
    await engine.syncOnReconnect();

    final pending = await db.outboundQueueDao.listPending();
    expect(pending, isEmpty);
  });
}
