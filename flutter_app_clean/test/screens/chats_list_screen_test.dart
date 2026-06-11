import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/di/app_services.dart';
import 'package:whatsbot_app/models/conversation.dart';
import 'package:whatsbot_app/models/message.dart';
import 'package:whatsbot_app/models/realtime_event.dart';
import 'package:whatsbot_app/screens/chats_list_screen.dart';
import 'package:whatsbot_app/services/realtime_service.dart';
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

  Future<void> seedConversations() async {
    final chats = AppServices.chatRepository;
    await chats.upsertConversation(
      Conversation(
        id: 1,
        businessId: 'default',
        customerWaId: '+5491111111001',
        customerName: 'Chat viejo',
        lastMessagePreview: 'Antiguo',
        lastMessageAt: DateTime.utc(2026, 6, 5, 9),
        updatedAt: DateTime.utc(2026, 6, 5, 9),
      ),
    );
    await chats.upsertConversation(
      Conversation(
        id: 2,
        businessId: 'default',
        customerWaId: '+5491111111002',
        customerName: 'Chat reciente',
        lastMessagePreview: 'Último',
        lastMessageAt: DateTime.utc(2026, 6, 5, 12),
        updatedAt: DateTime.utc(2026, 6, 5, 12),
      ),
    );
    await chats.upsertConversation(
      Conversation(
        id: 3,
        businessId: 'default',
        customerWaId: '+5491111111003',
        customerName: 'Chat medio',
        lastMessagePreview: 'Medio',
        lastMessageAt: DateTime.utc(2026, 6, 5, 10),
        updatedAt: DateTime.utc(2026, 6, 5, 10),
      ),
    );
  }

  List<String> listTitles(WidgetTester tester) {
    return tester
        .widgetList<ListTile>(find.byType(ListTile))
        .map((tile) => (tile.title as Text).data!)
        .toList();
  }

  testWidgets('ChatsListScreen muestra estado vacío sin conversaciones', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.textContaining('Aún no hay conversaciones'),
      findsOneWidget,
    );

    await disposeWidgetTree(tester);
  });

  testWidgets(
    'ChatsListScreen ordena tres conversaciones por lastMessageAt descendente',
    (WidgetTester tester) async {
      await seedConversations();

      await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(listTitles(tester), ['Chat reciente', 'Chat medio', 'Chat viejo']);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets('ChatsListScreen reordena al tope tras enviar mensaje', (
    WidgetTester tester,
  ) async {
    await seedConversations();

    await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await AppServices.messageRepository.sendMessage(
      conversationId: 3,
      customerWaId: '+5491111111003',
      body: 'Nuevo envío del dueño',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(listTitles(tester).first, 'Chat medio');

    final topTile = tester.widget<ListTile>(find.byType(ListTile).first);
    expect((topTile.subtitle as Text).data, 'Nuevo envío del dueño');

    await disposeWidgetTree(tester);
  });

  testWidgets(
    'ChatsListScreen reordena al recibir message.new aunque esté deduplicado (v1.18)',
    (WidgetTester tester) async {
      await seedConversations();

      final existing = ChatMessage(
        id: 900,
        conversationId: 1,
        direction: 'incoming',
        body: 'Cliente escribe',
        waId: '+5491111111001',
        isAdmin: false,
        channel: 'whatsapp',
        status: 'delivered',
        createdAt: DateTime.utc(2026, 6, 5, 14),
      );
      await AppServices.messageRepository.upsertMessage(existing);

      await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: existing,
          conversation: Conversation(
            id: 1,
            businessId: 'default',
            customerWaId: '+5491111111001',
            customerName: 'Chat viejo',
            lastMessagePreview: 'Cliente escribe',
            lastMessageAt: DateTime.utc(2026, 6, 5, 14),
            updatedAt: DateTime.utc(2026, 6, 5, 14),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(listTitles(tester).first, 'Chat viejo');
      expect(find.text('Cliente escribe'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatsListScreen actualiza preview con message.new y conversation_id servidor distinto (FIX 1b)',
    (WidgetTester tester) async {
      realtimeService.debugSetConnected(true);
      await seedConversations();

      await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await emitRealtimeEvent(
        RealtimeEvent(
          type: 'message.new',
          message: ChatMessage(
            id: 902,
            conversationId: 99,
            direction: 'incoming',
            body: 'Nuevo preview FIX 1b',
            waId: '+5491111111001',
            isAdmin: false,
            channel: 'whatsapp',
            status: 'delivered',
            createdAt: DateTime.utc(2026, 6, 5, 16),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(listTitles(tester).first, 'Chat viejo');
      expect(find.text('Nuevo preview FIX 1b'), findsOneWidget);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets(
    'ChatsListScreen abre ChatScreen con initialMessages desde caché (v1.16)',
    (WidgetTester tester) async {
      await AppServices.chatRepository.upsertConversation(
        Conversation(
          id: 1,
          businessId: 'default',
          customerWaId: '+5491111111001',
          customerName: 'Cliente cache',
          lastMessagePreview: 'Hola cache',
          lastMessageAt: DateTime.utc(2026, 6, 5, 11),
          updatedAt: DateTime.utc(2026, 6, 5, 11),
        ),
      );
      await AppServices.messageRepository.upsertMessage(
        ChatMessage(
          id: 55,
          conversationId: 1,
          direction: 'incoming',
          body: 'Hola cache',
          waId: '+5491111111001',
          isAdmin: false,
          channel: 'whatsapp',
          status: 'delivered',
          createdAt: DateTime.utc(2026, 6, 5, 11),
        ),
      );

      await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byType(ListTile));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('Hola cache'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);

      await disposeWidgetTree(tester);
    },
  );

  testWidgets('ChatsListScreen muestra error si el refresh falla', (
    WidgetTester tester,
  ) async {
    testApi.failConversations = true;

    await tester.pumpWidget(const MaterialApp(home: ChatsListScreen()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.drag(find.byType(ListView), const Offset(0, 200));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('Error de API simulado'), findsOneWidget);
    expect(find.text('Reintentar'), findsOneWidget);

    testApi.failConversations = false;
    await disposeWidgetTree(tester);
  });
}
