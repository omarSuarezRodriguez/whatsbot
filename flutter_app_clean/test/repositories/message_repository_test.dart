import 'package:drift/drift.dart' show Value;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/data/local/app_database.dart';
import 'package:whatsbot_app/data/repositories/message_repository.dart';
import 'package:whatsbot_app/models/message.dart';

import '../helpers/test_api_client.dart';

void main() {
  late AppDatabase db;
  late TestApiClient testApi;
  late MessageRepository repository;

  setUp(() async {
    db = AppDatabase.forTesting(NativeDatabase.memory());
    testApi = TestApiClient();
    await testApi.login();
    repository = MessageRepository(db, testApi.client);
  });

  tearDown(() async {
    await db.close();
  });

  test('sendMessage encola mensaje optimista si la API falla', () async {
    testApi.failSend = true;

    final result = await repository.sendMessage(
      conversationId: 1,
      customerWaId: '+5491111111111',
      body: 'Hola offline',
    );

    expect(result.queued, isTrue);
    expect(result.message.status, 'pending');
    expect(result.message.id, lessThan(0));

    final pending = await db.outboundQueueDao.listPending();
    expect(pending, hasLength(1));
    expect(pending.first.body, 'Hola offline');

    final local = await repository.watchMessages(1).first;
    expect(local, hasLength(1));
    expect(local.first.body, 'Hola offline');
  });

  test('sendMessage confirma mensaje y vacía cola si la API responde', () async {
    final result = await repository.sendMessage(
      conversationId: 1,
      customerWaId: '+5491111111111',
      body: 'Hola online',
    );

    expect(result.queued, isFalse);
    expect(result.message.id, greaterThan(0));

    final pending = await db.outboundQueueDao.listPending();
    expect(pending, isEmpty);

    final local = await repository.watchMessages(1).first;
    expect(local.single.body, 'Hola online');
    expect(local.single.id, result.message.id);
  });

  test('sendMessage conserva conversationId local si el servidor difiere', () async {
    final altApi = TestApiClient(sendConversationId: 99);
    await altApi.login();
    final altDb = AppDatabase.forTesting(NativeDatabase.memory());
    final altRepo = MessageRepository(altDb, altApi.client);

    final result = await altRepo.sendMessage(
      conversationId: 1,
      customerWaId: '+5491111111111',
      body: 'Hola con conv distinta',
    );

    expect(result.queued, isFalse);
    expect(result.message.conversationId, 1);

    final local = await altRepo.watchMessages(1).first;
    expect(local.single.body, 'Hola con conv distinta');
    expect(local.single.conversationId, 1);

    final otherConv = await altRepo.watchMessages(99).first;
    expect(otherConv, isEmpty);

    await altDb.close();
  });

  test('upsertMessageDeduped conserva conversationId tras WS con otro id', () async {
    final altApi = TestApiClient(sendConversationId: 99);
    await altApi.login();
    final altDb = AppDatabase.forTesting(NativeDatabase.memory());
    final altRepo = MessageRepository(altDb, altApi.client);

    final sendResult = await altRepo.sendMessage(
      conversationId: 1,
      customerWaId: '+5491111111111',
      body: 'Tras WS',
    );
    expect(sendResult.message.conversationId, 1);

    // Simula message.new del WS: mismo id, otra conversación, status delivered.
    await altRepo.upsertMessageDeduped(
      sendResult.message.copyWith(
        conversationId: 99,
        status: 'delivered',
        deliveredAt: DateTime.utc(2026, 6, 5, 14),
      ),
    );

    final local = await altRepo.watchMessages(1).first;
    expect(local.single.body, 'Tras WS');
    expect(local.single.conversationId, 1);
    expect(local.single.status, 'delivered');

    final otherConv = await altRepo.watchMessages(99).first;
    expect(otherConv, isEmpty);

    await altDb.close();
  });

  test('flushOutboundQueue reenvía mensajes pendientes', () async {
    testApi.failSend = true;
    await repository.sendMessage(
      conversationId: 1,
      customerWaId: '+5491111111111',
      body: 'Pendiente',
    );

    testApi.failSend = false;
    await repository.flushOutboundQueue();

    final pending = await db.outboundQueueDao.listPending();
    expect(pending, isEmpty);

    final local = await repository.watchMessages(1).first;
    expect(local.single.id, greaterThan(0));
    expect(local.single.status, 'sent');
  });

  test('needsSyncFromApi true sin caché y false tras sync reciente', () async {
    expect(await repository.needsSyncFromApi(1), isTrue);

    await repository.upsertMessage(
      ChatMessage(
        id: 1,
        conversationId: 1,
        direction: 'incoming',
        body: 'Hola',
        waId: '+5491111111111',
        isAdmin: false,
        channel: 'whatsapp',
        status: 'delivered',
        createdAt: DateTime.utc(2026, 1, 1, 12),
      ),
    );
    await db.syncCursorDao.setCursor('messages_sync_at:1', '1');

    expect(await repository.needsSyncFromApi(1), isFalse);
  });

  test('resolveForLocalStore prefiere hilo local por wa_id', () async {
    final now = DateTime.utc(2026, 6, 5, 12);
    await db.conversationDao.upsert(
      ConversationsCompanion(
        id: const Value(1),
        businessId: const Value('default'),
        customerWaId: const Value('+5491111111111'),
        updatedAt: Value(now),
        syncedAt: Value(now),
      ),
    );
    await db.conversationDao.upsert(
      ConversationsCompanion(
        id: const Value(99),
        businessId: const Value('default'),
        customerWaId: const Value('+5498888888888'),
        updatedAt: Value(now),
        syncedAt: Value(now),
      ),
    );

    final resolved = await repository.resolveForLocalStore(
      ChatMessage(
        id: 501,
        conversationId: 99,
        direction: 'incoming',
        body: 'WS con id servidor distinto',
        waId: '+5491111111111',
        isAdmin: false,
        channel: 'whatsapp',
        status: 'delivered',
        createdAt: now,
      ),
    );

    expect(resolved.conversationId, 1);
  });

  test('upsertMessageDeduped omite mensajes idénticos', () async {
    final message = ChatMessage(
      id: 50,
      conversationId: 1,
      direction: 'incoming',
      body: 'Hola',
      waId: '+5491111111111',
      isAdmin: false,
      channel: 'whatsapp',
      status: 'delivered',
      createdAt: DateTime.utc(2026, 1, 1, 12),
    );

    expect(await repository.upsertMessageDeduped(message), isTrue);
    expect(await repository.upsertMessageDeduped(message), isFalse);
  });
}
