import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/data/local/app_database.dart';
import 'package:whatsbot_app/data/repositories/chat_repository.dart';
import 'package:whatsbot_app/data/repositories/message_repository.dart';
import 'package:whatsbot_app/data/sync/sync_engine.dart';
import 'package:whatsbot_app/di/app_services.dart';
import 'package:whatsbot_app/models/conversation.dart';
import 'package:whatsbot_app/models/message.dart';
import 'package:whatsbot_app/models/realtime_event.dart';
import 'package:whatsbot_app/services/realtime_service.dart';

import '../helpers/test_api_client.dart';

/// Simula instalación nueva → carga inicial → mensajes en vivo sin polling.
void main() {
  late AppDatabase db;
  late TestApiClient testApi;
  final notifiedBodies = <String>[];

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    notifiedBodies.clear();
    realtimeService.disableSocketForTesting = true;

    testApi = TestApiClient(
      conversations: [
        {
          'id': 1,
          'business_id': 'default',
          'customer_wa_id': '+573001112233',
          'customer_name': 'Cliente Uno',
          'last_message_preview': 'Hola inicial',
          'last_message_at': DateTime.utc(2026, 6, 5, 10).toIso8601String(),
          'updated_at': DateTime.utc(2026, 6, 5, 10).toIso8601String(),
        },
      ],
      messagesByConversation: {
        1: [
          {
            'id': 10,
            'conversation_id': 1,
            'direction': 'incoming',
            'body': 'Hola inicial',
            'wa_id': '+573001112233',
            'is_admin': false,
            'channel': 'whatsapp',
            'status': 'delivered',
            'created_at': DateTime.utc(2026, 6, 5, 10).toIso8601String(),
          },
        ],
      },
    );
    await testApi.login();

    db = AppDatabase.forTesting(NativeDatabase.memory());
    AppServices.database = db;
    AppServices.chatRepository = ChatRepository(db, testApi.client);
    AppServices.messageRepository = MessageRepository(db, testApi.client);
    AppServices.syncEngine = SyncEngine(
      AppServices.chatRepository,
      AppServices.messageRepository,
    );

    realtimeService.onReconnectSync = AppServices.syncEngine.syncOnReconnect;
    realtimeService.persistEvent = AppServices.syncEngine.handleRealtimeEvent;
    realtimeService.connectivityOnline = () => true;
    AppServices.syncEngine.onIncomingMessage = (conv, msg) async {
      notifiedBodies.add(msg.body);
    };
  });

  tearDown(() async {
    AppServices.stopForegroundFallback();
    await realtimeService.disconnect();
    await db.close();
  });

  Future<void> emitIncoming({
    required int id,
    required String body,
    DateTime? at,
  }) {
    final createdAt = at ?? DateTime.utc(2026, 6, 5, 12, id);
    return realtimeService.debugEmitEvent(
      RealtimeEvent(
        type: 'message.new',
        message: ChatMessage(
          id: id,
          conversationId: 1,
          direction: 'incoming',
          body: body,
          waId: '+573001112233',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: createdAt,
        ),
        conversation: Conversation(
          id: 1,
          businessId: 'default',
          customerWaId: '+573001112233',
          customerName: 'Cliente Uno',
          lastMessagePreview: body,
          lastMessageAt: createdAt,
          updatedAt: createdAt,
        ),
      ),
    );
  }

  test('tras hidratación inicial, segundo mensaje WS actualiza lista y SQLite', () async {
    // 1) Carga inicial (instalación nueva / login)
    await AppServices.syncEngine.syncOnReconnect();
    final afterHydrate = await AppServices.chatRepository
        .watchConversations()
        .first;
    expect(afterHydrate, hasLength(1));
    expect(afterHydrate.first.lastMessagePreview, 'Hola inicial');

    // 2) Mensaje en vivo #1
    await emitIncoming(id: 20, body: 'Mensaje en vivo 1');
    final afterFirst = await AppServices.chatRepository
        .watchConversations()
        .first;
    expect(afterFirst.first.lastMessagePreview, 'Mensaje en vivo 1');

    final msgs1 = await AppServices.messageRepository.watchMessages(1).first;
    expect(msgs1.map((m) => m.body), contains('Mensaje en vivo 1'));

    // 3) Mensaje en vivo #2 (el caso que fallaba: solo cargaba al inicio)
    await emitIncoming(id: 21, body: 'Mensaje en vivo 2');
    final afterSecond = await AppServices.chatRepository
        .watchConversations()
        .first;
    expect(afterSecond.first.lastMessagePreview, 'Mensaje en vivo 2');

    final msgs2 = await AppServices.messageRepository.watchMessages(1).first;
    expect(
      msgs2.map((m) => m.body),
      containsAll(['Mensaje en vivo 1', 'Mensaje en vivo 2']),
    );
    expect(notifiedBodies, containsAll(['Mensaje en vivo 1', 'Mensaje en vivo 2']));
  });

  test('syncOnReconnect concurrente no rompe el estado (mutex)', () async {
    await AppServices.chatRepository.upsertConversation(
      Conversation(
        id: 1,
        businessId: 'default',
        customerWaId: '+573001112233',
        updatedAt: DateTime.utc(2026, 6, 5, 9),
      ),
    );

    await Future.wait([
      AppServices.syncEngine.syncOnReconnect(),
      AppServices.syncEngine.syncOnReconnect(),
      AppServices.syncEngine.syncOnReconnect(),
    ]);

    final convs = await AppServices.chatRepository.watchConversations().first;
    expect(convs, isNotEmpty);
  });

  test('mensaje WS con conversation_id distinto se guarda en hilo local', () async {
    await AppServices.chatRepository.upsertConversation(
      Conversation(
        id: 5,
        businessId: 'default',
        customerWaId: '+573001112233',
        customerName: 'Local',
        lastMessagePreview: 'Previo',
        lastMessageAt: DateTime.utc(2026, 6, 5, 9),
        updatedAt: DateTime.utc(2026, 6, 5, 9),
      ),
    );

    await realtimeService.debugEmitEvent(
      RealtimeEvent(
        type: 'message.new',
        message: ChatMessage(
          id: 99,
          conversationId: 999,
          direction: 'incoming',
          body: 'Desde otro conv_id',
          waId: '+573001112233',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: DateTime.utc(2026, 6, 5, 14),
        ),
      ),
    );

    final local = await AppServices.messageRepository.watchMessages(5).first;
    expect(local.any((m) => m.body == 'Desde otro conv_id'), isTrue);

    final wrong = await AppServices.messageRepository.watchMessages(999).first;
    expect(wrong, isEmpty);
  });
}
