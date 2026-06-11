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
import 'package:whatsbot_app/services/api_client.dart';
import 'package:whatsbot_app/services/message_alerts_service.dart';
import 'package:whatsbot_app/services/realtime_service.dart';

import 'test_api_client.dart';

/// Arranca AppServices con SQLite en memoria y API mock para widget tests.
Future<TestApiClient> setUpTestAppServices() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  realtimeService.disableSocketForTesting = true;
  final testApi = TestApiClient();
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
  realtimeService.onReconnectSync = AppServices.syncEngine.syncOnReconnect;
  realtimeService.persistEvent = AppServices.syncEngine.handleRealtimeEvent;
  realtimeService.connectivityOnline = () => true;
  realtimeService.shouldSyncOnConnect = () => true;
  AppServices.syncEngine.onIncomingMessage = (
    Conversation conversation,
    ChatMessage message,
  ) {
    return messageAlerts.handleRealtimeMessage(
      conversation: conversation,
      message: message,
    );
  };

  await realtimeService.disconnect();
  return testApi;
}

Future<void> tearDownTestAppServices() async {
  await realtimeService.disconnect();
  realtimeService.disableSocketForTesting = false;
  if (AppServices.isInitialized) {
    try {
      await AppServices.database.close();
    } catch (_) {}
  }
}

/// Cierra pantallas y drena timers de Drift/WS antes del dispose del test.
Future<void> disposeWidgetTree(WidgetTester tester) async {
  await realtimeService.disconnect();
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
  try {
    await AppServices.database.close();
  } catch (_) {}
}
