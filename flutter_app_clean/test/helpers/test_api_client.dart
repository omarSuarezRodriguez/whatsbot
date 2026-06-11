import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:whatsbot_app/services/api_client.dart';

/// Cliente HTTP fake para tests de repositorios offline-first.
class TestApiClient {
  TestApiClient({
    this.failSend = false,
    this.failConversations = false,
    this.sendConversationId = 1,
    List<Map<String, dynamic>>? conversations,
    Map<int, List<Map<String, dynamic>>>? messagesByConversation,
  })  : conversations = List<Map<String, dynamic>>.from(conversations ?? []),
        messagesByConversation = Map<int, List<Map<String, dynamic>>>.from(
          messagesByConversation ?? {},
        );

  bool failSend;
  bool failConversations;
  final int sendConversationId;
  final List<Map<String, dynamic>> conversations;
  final Map<int, List<Map<String, dynamic>>> messagesByConversation;
  int _nextMessageId = 1000;

  late final MockClient mockHttp = _buildMockClient();
  late final ApiClient client = ApiClient(httpClient: mockHttp);

  Future<void> login() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await client.login('default', 'pin');
  }

  MockClient _buildMockClient() {
    return MockClient((request) async {
      final path = request.url.path;

      if (path.endsWith('/auth/login')) {
        return http.Response(
          jsonEncode({
            'access_token': 'test-token',
            'token_type': 'bearer',
            'business_id': 'default',
            'business_name': 'Test Business',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }

      if (path.endsWith('/whatsbot/conversations') && request.method == 'GET') {
        if (failConversations) {
          return http.Response(
            jsonEncode({'detail': 'Error de API simulado'}),
            503,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode(conversations),
          200,
          headers: {'content-type': 'application/json'},
        );
      }

      final readMatch = RegExp(
        r'/whatsbot/conversations/(\d+)/mark-read$',
      ).firstMatch(path);
      if (readMatch != null && request.method == 'POST') {
        return http.Response('', 204);
      }

      final messagesMatch = RegExp(
        r'/whatsbot/conversations/(\d+)/messages$',
      ).firstMatch(path);
      if (messagesMatch != null && request.method == 'GET') {
        final convId = int.parse(messagesMatch.group(1)!);
        final list = messagesByConversation[convId] ?? [];
        return http.Response(
          jsonEncode(list),
          200,
          headers: {'content-type': 'application/json'},
        );
      }

      if (path.endsWith('/whatsbot/messages') && request.method == 'POST') {
        if (failSend) {
          return http.Response(
            jsonEncode({'detail': 'Sin conexión'}),
            503,
            headers: {'content-type': 'application/json'},
          );
        }

        final body = jsonDecode(request.body) as Map<String, dynamic>;
        final clientId = body['client_id'] as String?;
        if (clientId != null && clientId.isNotEmpty) {
          for (final list in messagesByConversation.values) {
            for (final item in list) {
              if (item['client_id'] == clientId) {
                return http.Response(
                  jsonEncode(item),
                  201,
                  headers: {'content-type': 'application/json'},
                );
              }
            }
          }
        }

        final id = _nextMessageId++;
        final message = {
          'id': id,
          'conversation_id': sendConversationId,
          'direction': 'outgoing',
          'body': body['body'],
          'wa_id': body['customer_wa_id'],
          'is_admin': true,
          'channel': 'whatsapp',
          'status': 'sent',
          'created_at': DateTime.now().toUtc().toIso8601String(),
          'client_id': clientId,
        };
        messagesByConversation
            .putIfAbsent(sendConversationId, () => [])
            .add(message);
        return http.Response(
          jsonEncode(message),
          201,
          headers: {'content-type': 'application/json'},
        );
      }

      return http.Response('[]', 200);
    });
  }
}
