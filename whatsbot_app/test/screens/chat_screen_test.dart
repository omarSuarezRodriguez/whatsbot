import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/data/local/app_database.dart';
import 'package:whatsbot_app/data/repositories/chat_repository.dart';
import 'package:whatsbot_app/data/repositories/message_repository.dart';
import 'package:whatsbot_app/data/sync/sync_engine.dart';
import 'package:whatsbot_app/di/app_services.dart';
import 'package:whatsbot_app/models/conversation.dart';
import 'package:whatsbot_app/models/message.dart';
import 'package:whatsbot_app/models/realtime_event.dart';
import 'package:whatsbot_app/screens/chat_screen.dart';
import 'package:whatsbot_app/services/api_client.dart';
import 'package:whatsbot_app/services/realtime_service.dart';
import 'package:whatsbot_app/widgets/message_bubble.dart';

import '../helpers/realtime_test_helper.dart';
import '../helpers/test_api_client.dart';
import '../helpers/test_app_services.dart';

void main() {
  late TestApiClient testApi;

  setUp(() async {
    testApi = await setUpTestAppServices();
  });

  tearDown(() async {
    await tearDownTestAppServices();
  });

  Conversation conversation({String customerWaId = '+5491111111111'}) {
    return Conversation(
      id: 1,
      businessId: 'default',
      customerWaId: customerWaId,
      customerName: 'Omar Suarez',
      updatedAt: DateTime.utc(2026, 6, 5, 10),
    );
  }

  List<ChatMessage> sampleMessages() {
    return [
      ChatMessage(
        id: 1,
        conversationId: 1,
        direction: 'incoming',
        body: 'Hola desde el cliente',
        waId: '+5491111111111',
        isAdmin: false,
        channel: 'whatsapp',
        status: 'delivered',
        createdAt: DateTime.utc(2026, 6, 5, 10, 28),
      ),
      ChatMessage(
        id: 2,
        conversationId: 1,
        direction: 'outgoing',
        body: 'Respuesta del admin',
        waId: '+5491111111111',
        isAdmin: true,
        channel: 'whatsapp',
        status: 'sent',
        createdAt: DateTime.utc(2026, 6, 5, 10, 29),
      ),
    ];
  }

  Future<void> seedMessages([List<ChatMessage>? messages]) async {
    for (final message in messages ?? sampleMessages()) {
      await AppServices.messageRepository.upsertMessage(message);
    }
  }

  Future<void> pumpChatScreen(
    WidgetTester tester, {
    List<ChatMessage>? initialMessages,
    bool fromSqliteOnly = false,
    bool seedSqlite = false,
  }) async {
    final messages = initialMessages ?? sampleMessages();
    if (fromSqliteOnly || seedSqlite) {
      await seedMessages(messages);
    }

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          conversation: conversation(),
          initialMessages: fromSqliteOnly ? null : initialMessages,
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('ChatScreen muestra mensajes desde SQLite', (
    WidgetTester tester,
  ) async {
    await pumpChatScreen(tester, fromSqliteOnly: true);
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Hola desde el cliente'), findsOneWidget);
    expect(find.text('Respuesta del admin'), findsOneWidget);
    expect(find.text('Omar Suarez'), findsOneWidget);

    await disposeWidgetTree(tester);
  });

  testWidgets(
    'ChatScreen con initialMessages muestra el último mensaje en el primer frame (v1.16)',
    (WidgetTester tester) async {
      final messages = sampleMessages();
      await seedMessages(messages);

      await pumpChatScreen(tester, initialMessages: messages);

      expect(find.text('Respuesta del admin'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);

      final listView = tester.widget<ListView>(find.byType(ListView));
      expect(listView.reverse, isTrue);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen con caché SQLite no muestra spinner superpuesto (v1.16)',
    (WidgetTester tester) async {
      await pumpChatScreen(tester, fromSqliteOnly: true);
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Respuesta del admin'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen ordena mensajes con mismo createdAt por id estable (v1.18)',
    (WidgetTester tester) async {
      final sameTime = DateTime.utc(2026, 6, 5, 12);
      final messages = [
        ChatMessage(
          id: 10,
          conversationId: 1,
          direction: 'incoming',
          body: 'Primero por id',
          waId: '+5491111111111',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: sameTime,
        ),
        ChatMessage(
          id: 20,
          conversationId: 1,
          direction: 'outgoing',
          body: 'Segundo por id',
          waId: '+5491111111111',
          isAdmin: true,
          channel: 'whatsapp',
          status: 'sent',
          createdAt: sameTime,
        ),
        ChatMessage(
          id: 30,
          conversationId: 1,
          direction: 'incoming',
          body: 'Tercero por id',
          waId: '+5491111111111',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: sameTime,
        ),
      ];

      await seedMessages(messages);
      await pumpChatScreen(tester, initialMessages: messages);

      final bubbles = tester
          .widgetList<MessageBubble>(find.byType(MessageBubble))
          .map((bubble) => bubble.message.id)
          .toList();

      expect(bubbles, [30, 20, 10]);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen muestra mensaje entrante en vivo sin reabrir (v1.17)',
    (WidgetTester tester) async {
      await pumpChatScreen(tester, initialMessages: const []);

      expect(find.text('Mensaje en vivo'), findsNothing);

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: ChatMessage(
            id: 501,
            conversationId: 1,
            direction: 'incoming',
            body: 'Mensaje en vivo',
            waId: '+5491111111111',
            isAdmin: false,
            channel: 'whatsapp',
            status: 'delivered',
            createdAt: DateTime.utc(2026, 6, 5, 12, 30),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Mensaje en vivo'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen con initialMessages en caché muestra mensaje nuevo en vivo (regresión StreamBuilder)',
    (WidgetTester tester) async {
      final cached = sampleMessages();
      await seedMessages(cached);

      await pumpChatScreen(tester, initialMessages: cached);

      expect(find.text('Respuesta del admin'), findsOneWidget);
      expect(find.text('Llegó con caché precargada'), findsNothing);

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: ChatMessage(
            id: 502,
            conversationId: 1,
            direction: 'incoming',
            body: 'Llegó con caché precargada',
            waId: '+5491111111111',
            isAdmin: false,
            channel: 'whatsapp',
            status: 'delivered',
            createdAt: DateTime.utc(2026, 6, 5, 12, 31),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Hola desde el cliente'), findsOneWidget);
      expect(find.text('Respuesta del admin'), findsOneWidget);
      expect(find.text('Llegó con caché precargada'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen con initialMessages actualiza al cambiar SQLite sin reabrir',
    (WidgetTester tester) async {
      final cached = sampleMessages();
      await seedMessages(cached);

      await pumpChatScreen(tester, initialMessages: cached);
      expect(find.text('Actualizado por Drift'), findsNothing);

      await AppServices.messageRepository.upsertMessage(
        ChatMessage(
          id: 503,
          conversationId: 1,
          direction: 'incoming',
          body: 'Actualizado por Drift',
          waId: '+5491111111111',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: DateTime.utc(2026, 6, 5, 12, 32),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Actualizado por Drift'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen reemplaza burbuja optimista por confirmada vía clientUuid (v1.24)',
    (WidgetTester tester) async {
      await pumpChatScreen(tester, initialMessages: const []);

      await tester.enterText(find.byType(TextField), 'Envío confirmado');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(find.text('Envío confirmado'), findsOneWidget);
      expect(
        tester
            .widgetList<MessageBubble>(find.byType(MessageBubble))
            .where((b) => b.message.body == 'Envío confirmado')
            .length,
        1,
      );

      await disposeWidgetTree(tester);
    },
  );

  testWidgets('ChatScreen muestra burbuja optimista al enviar sin duplicar', (
    WidgetTester tester,
  ) async {
    await pumpChatScreen(tester, initialMessages: const []);

    await tester.enterText(find.byType(TextField), 'Mensaje de prueba');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pump();

    expect(find.text('Mensaje de prueba'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('Mensaje de prueba'), findsOneWidget);

    await disposeWidgetTree(tester);
  });

  testWidgets(
    'ChatScreen muestra mensaje enviado aunque el servidor use otro conversation_id',
    (WidgetTester tester) async {
      await tearDownTestAppServices();
      final testApi = TestApiClient(sendConversationId: 99);
      apiClient.replaceHttpClient(testApi.mockHttp);
      await testApi.login();
      await apiClient.login('default', 'pin');

      final db = AppDatabase.forTesting(NativeDatabase.memory());
      AppServices.database = db;
      AppServices.chatRepository = ChatRepository(db, apiClient);
      AppServices.messageRepository = MessageRepository(db, apiClient);
      AppServices.syncEngine = SyncEngine(
        AppServices.chatRepository,
        AppServices.messageRepository,
      );
      realtimeService.disableSocketForTesting = true;

      await pumpChatScreen(tester, initialMessages: const []);

      await tester.enterText(find.byType(TextField), 'Kekeke');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(find.text('Kekeke'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets('ChatScreen usa TextCapitalization.sentences en el TextField', (
    WidgetTester tester,
  ) async {
    await pumpChatScreen(tester, initialMessages: const []);

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.textCapitalization, TextCapitalization.sentences);

    await disposeWidgetTree(tester);
  });

  testWidgets(
    'ChatScreen muestra message.new con conversation_id servidor distinto (FIX 1b)',
    (WidgetTester tester) async {
      realtimeService.debugSetConnected(true);
      await AppServices.chatRepository.upsertConversation(conversation());

      await pumpChatScreen(tester, initialMessages: const []);

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: ChatMessage(
            id: 777,
            conversationId: 99,
            direction: 'incoming',
            body: 'Por wa_id local',
            waId: '+5491111111111',
            isAdmin: false,
            channel: 'whatsapp',
            status: 'delivered',
            createdAt: DateTime.utc(2026, 6, 5, 14),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Por wa_id local'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen con WS caído trae mensaje nuevo vía REST sin reabrir',
    (WidgetTester tester) async {
      realtimeService.debugSetConnected(false);

      testApi.messagesByConversation[1] = [
        {
          'id': 10,
          'conversation_id': 1,
          'direction': 'incoming',
          'body': 'Historial cacheado',
          'wa_id': '+5491111111111',
          'is_admin': false,
          'channel': 'whatsapp',
          'status': 'delivered',
          'created_at': DateTime.utc(2026, 6, 5, 10).toIso8601String(),
        },
      ];
      await AppServices.messageRepository.refreshFromApi(1, incremental: true);

      testApi.messagesByConversation[1] = [
        ...testApi.messagesByConversation[1]!,
        {
          'id': 11,
          'conversation_id': 1,
          'direction': 'incoming',
          'body': 'Nuevo vía REST',
          'wa_id': '+5491111111111',
          'is_admin': false,
          'channel': 'whatsapp',
          'status': 'delivered',
          'created_at': DateTime.utc(2026, 6, 5, 10, 5).toIso8601String(),
        },
      ];

      await pumpChatScreen(tester, fromSqliteOnly: true);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('Historial cacheado'), findsOneWidget);
      expect(find.text('Nuevo vía REST'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen con wa_id sin + y caché precargada muestra entrante y bot en vivo',
    (WidgetTester tester) async {
      const omarWa = '35699155990';
      final cached = [
        ChatMessage(
          id: 1,
          conversationId: 1,
          direction: 'incoming',
          body: 'kmk',
          waId: omarWa,
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: DateTime.utc(2026, 6, 5, 10, 28),
        ),
        ChatMessage(
          id: 2,
          conversationId: 1,
          direction: 'outgoing',
          body: 'Respuesta automática',
          waId: omarWa,
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: DateTime.utc(2026, 6, 5, 10, 29),
        ),
      ];

      await AppServices.chatRepository.upsertConversation(
        conversation(customerWaId: omarWa),
      );
      await seedMessages(cached);

      await tester.pumpWidget(
        MaterialApp(
          home: ChatScreen(
            conversation: conversation(customerWaId: omarWa),
            initialMessages: cached,
          ),
        ),
      );
      await tester.pump();

      expect(find.text('kmk'), findsOneWidget);
      expect(find.text('jkmnl'), findsNothing);

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: ChatMessage(
            id: 601,
            conversationId: 99,
            direction: 'incoming',
            body: 'jkmnl',
            waId: '+$omarWa',
            isAdmin: false,
            channel: 'whatsapp',
            status: 'delivered',
            createdAt: DateTime.utc(2026, 6, 5, 12, 40),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('jkmnl'), findsOneWidget);

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: ChatMessage(
            id: 602,
            conversationId: 99,
            direction: 'outgoing',
            body: 'Respuesta bot en vivo',
            waId: omarWa,
            isAdmin: false,
            channel: 'whatsapp',
            status: 'delivered',
            createdAt: DateTime.utc(2026, 6, 5, 12, 41),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Respuesta bot en vivo'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatScreen reconcilia tras refresh cuando llegan mensajes vía REST',
    (WidgetTester tester) async {
      realtimeService.debugSetConnected(true);

      final cached = sampleMessages();
      await seedMessages(cached);
      testApi.messagesByConversation[1] = [
        {
          'id': 1,
          'conversation_id': 1,
          'direction': 'incoming',
          'body': 'Hola desde el cliente',
          'wa_id': '+5491111111111',
          'is_admin': false,
          'channel': 'whatsapp',
          'status': 'delivered',
          'created_at': DateTime.utc(2026, 6, 5, 10, 28).toIso8601String(),
        },
        {
          'id': 2,
          'conversation_id': 1,
          'direction': 'outgoing',
          'body': 'Respuesta del admin',
          'wa_id': '+5491111111111',
          'is_admin': true,
          'channel': 'whatsapp',
          'status': 'sent',
          'created_at': DateTime.utc(2026, 6, 5, 10, 29).toIso8601String(),
        },
      ];

      await pumpChatScreen(tester, initialMessages: cached);
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Solo en SQLite tras sync'), findsNothing);

      testApi.messagesByConversation[1] = [
        ...testApi.messagesByConversation[1]!,
        {
          'id': 11,
          'conversation_id': 1,
          'direction': 'incoming',
          'body': 'Solo en SQLite tras sync',
          'wa_id': '+5491111111111',
          'is_admin': false,
          'channel': 'whatsapp',
          'status': 'delivered',
          'created_at': DateTime.utc(2026, 6, 5, 12, 45).toIso8601String(),
        },
      ];

      realtimeService.debugSetConnected(false);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Solo en SQLite tras sync'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets('ChatScreen muestra mensaje admin tras confirmación en SQLite', (
    WidgetTester tester,
  ) async {
    await AppServices.messageRepository.upsertMessage(
      ChatMessage(
        id: 42,
        conversationId: 1,
        direction: 'outgoing',
        body: 'Admin confirmado',
        waId: '+5491111111111',
        isAdmin: true,
        channel: 'whatsapp',
        status: 'sent',
        createdAt: DateTime.utc(2026, 6, 5, 11),
        clientUuid: 'uuid-admin-confirmado',
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          conversation: conversation(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Admin confirmado'), findsOneWidget);

    await disposeWidgetTree(tester);
  });
}
