import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config/api_config.dart';
import '../models/business.dart';
import '../models/conversation.dart';
import '../models/customer.dart';
import '../models/menu_item.dart';
import '../models/message.dart';
import '../models/order.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

/// Cliente HTTP para la API WhatsBot (Fase 7). Sin secrets Twilio.
class ApiClient {
  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  http.Client _http;

  /// Sustituye el cliente HTTP (solo tests widget/integration).
  void replaceHttpClient(http.Client client) {
    _http = client;
  }
  String? _token;
  String? businessId;
  String? businessName;

  static const _tokenKey = 'whatsbot_access_token';
  static const _businessIdKey = 'whatsbot_business_id';
  static const _businessNameKey = 'whatsbot_business_name';
  static const Duration _requestTimeout = Duration(seconds: 12);

  Future<T> _withTimeout<T>(Future<T> future) {
    return future.timeout(
      _requestTimeout,
      onTimeout: () => throw ApiException(
        'Sin respuesta del servidor. Revisa la conexión o la URL de la API.',
      ),
    );
  }

  bool get isLoggedIn => _token != null && _token!.isNotEmpty;

  String? get accessToken => _token;

  Map<String, String> get _authHeaders => {
        'Content-Type': 'application/json',
        ...ApiConfig.connectionHeaders,
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Uri _uri(String path, [Map<String, String>? query]) {
    return Uri.parse('${ApiConfig.apiBaseUrl}$path').replace(queryParameters: query);
  }

  Future<void> loadSession() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString(_tokenKey);
    businessId = prefs.getString(_businessIdKey);
    businessName = prefs.getString(_businessNameKey);
  }

  Future<void> _saveSession(LoginResult result) async {
    _token = result.accessToken;
    businessId = result.businessId;
    businessName = result.businessName;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, result.accessToken);
    await prefs.setString(_businessIdKey, result.businessId);
    await prefs.setString(_businessNameKey, result.businessName);
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    _token = null;
    businessId = null;
    businessName = null;
    await prefs.remove(_tokenKey);
    await prefs.remove(_businessIdKey);
    await prefs.remove(_businessNameKey);
  }

  Future<LoginResult> login(String businessIdInput, String pin) async {
    final response = await _withTimeout(
      _http.post(
        _uri('/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'business_id': businessIdInput, 'pin': pin}),
      ),
    );
    if (response.statusCode == 200) {
      final result = LoginResult.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
      await _saveSession(result);
      return result;
    }
    throw _errorFromResponse(response, 'No se pudo iniciar sesión');
  }

  Future<List<Conversation>> getConversations({DateTime? since}) async {
    final query = since != null
        ? {'since': since.toUtc().toIso8601String()}
        : null;
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/conversations', query),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => Conversation.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> markConversationRead(int conversationId) async {
    final response = await _withTimeout(
      _http.post(
        _uri('/whatsbot/conversations/$conversationId/mark-read'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response, expected: {204, 200});
  }

  Future<List<ChatMessage>> getMessages(
    int conversationId, {
    int? afterId,
  }) async {
    final query =
        afterId != null ? {'after_id': afterId.toString()} : null;
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/conversations/$conversationId/messages', query),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => ChatMessage.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ChatMessage> sendMessage({
    required String customerWaId,
    required String body,
    String? clientId,
  }) async {
    final payload = <String, dynamic>{
      'customer_wa_id': customerWaId,
      'body': body,
    };
    if (clientId != null && clientId.isNotEmpty) {
      payload['client_id'] = clientId;
    }
    final response = await _withTimeout(
      _http.post(
        _uri('/whatsbot/messages'),
        headers: _authHeaders,
        body: jsonEncode(payload),
      ),
    );
    _ensureOk(response, expected: {201, 200});
    return ChatMessage.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<PendingOrder>> getPendingOrders() async {
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/orders/pending'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => PendingOrder.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<String> approveOrder(String orderId) async {
    final response = await _withTimeout(
      _http.post(
        _uri('/whatsbot/orders/$orderId/approve'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    if (data['ok'] != true) {
      throw ApiException(
        data['message'] as String? ?? 'No se pudo confirmar el pedido',
        statusCode: response.statusCode,
      );
    }
    return data['message'] as String? ?? 'Pedido aprobado';
  }

  Future<void> registerDeviceToken({
    required String token,
    required String platform,
  }) async {
    final response = await _withTimeout(
      _http.post(
        _uri('/whatsbot/device-token'),
        headers: _authHeaders,
        body: jsonEncode({'token': token, 'platform': platform}),
      ),
    );
    _ensureOk(response, expected: {204, 200});
  }

  Future<void> unregisterDeviceToken({
    required String token,
    required String platform,
  }) async {
    final request = http.Request('DELETE', _uri('/whatsbot/device-token'));
    request.headers.addAll(_authHeaders);
    request.body = jsonEncode({'token': token, 'platform': platform});
    final streamed = await _withTimeout(_http.send(request));
    final response = await _withTimeout(http.Response.fromStream(streamed));
    _ensureOk(response, expected: {204, 200});
  }

  Future<String> rejectOrder(String orderId, {String reason = ''}) async {
    final response = await _withTimeout(
      _http.post(
        _uri('/whatsbot/orders/$orderId/reject', {'reason': reason}),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return data['message'] as String? ?? 'Pedido rechazado';
  }

  Future<BusinessProfile> getBusinessMe() async {
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/business/me'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    return BusinessProfile.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<MenuItemModel>> getMenu() async {
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/business/menu'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final items = data['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => MenuItemModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<MenuItemModel>> saveMenu(List<MenuItemModel> items) async {
    final response = await _withTimeout(
      _http.put(
        _uri('/whatsbot/business/menu'),
        headers: _authHeaders,
        body: jsonEncode({
          'items': items.map((i) => i.toApiJson()).toList(),
        }),
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final saved = data['items'] as List<dynamic>? ?? [];
    return saved
        .map((e) => MenuItemModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Map<String, dynamic>> getIntents() async {
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/business/intents'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return Map<String, dynamic>.from(data['config'] as Map? ?? {});
  }

  Future<Map<String, dynamic>> saveIntents(Map<String, dynamic> config) async {
    final response = await _withTimeout(
      _http.put(
        _uri('/whatsbot/business/intents'),
        headers: _authHeaders,
        body: jsonEncode({'config': config}),
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return Map<String, dynamic>.from(data['config'] as Map? ?? {});
  }

  Future<Map<String, String>> getPrompts() async {
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/business/prompts'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final config = data['config'] as Map? ?? {};
    return config.map((k, v) => MapEntry(k.toString(), v.toString()));
  }

  Future<Map<String, String>> savePrompts(Map<String, String> config) async {
    final response = await _withTimeout(
      _http.put(
        _uri('/whatsbot/business/prompts'),
        headers: _authHeaders,
        body: jsonEncode({'config': config}),
      ),
    );
    _ensureOk(response);
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final saved = data['config'] as Map? ?? {};
    return saved.map((k, v) => MapEntry(k.toString(), v.toString()));
  }

  // ----------------------------------------------------------------- Customers

  Future<List<Customer>> getCustomers({String? search}) async {
    final query = search != null && search.isNotEmpty ? {'search': search} : null;
    final response = await _withTimeout(
      _http.get(
        _uri('/whatsbot/customers', query),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list.map((e) => Customer.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Customer> createCustomer({
    required String waId,
    String? name,
    String? phone,
    String? notes,
  }) async {
    final payload = <String, dynamic>{'wa_id': waId};
    if (name != null) payload['name'] = name;
    if (phone != null) payload['phone'] = phone;
    if (notes != null) payload['notes'] = notes;
    final response = await _withTimeout(
      _http.post(
        _uri('/whatsbot/customers'),
        headers: _authHeaders,
        body: jsonEncode(payload),
      ),
    );
    _ensureOk(response, expected: {201, 200});
    return Customer.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<Customer> updateCustomer(
    int customerId, {
    String? name,
    String? phone,
    String? notes,
    bool? blocked,
  }) async {
    final payload = <String, dynamic>{};
    if (name != null) payload['name'] = name;
    if (phone != null) payload['phone'] = phone;
    if (notes != null) payload['notes'] = notes;
    if (blocked != null) payload['blocked'] = blocked;
    final response = await _withTimeout(
      _http.put(
        _uri('/whatsbot/customers/$customerId'),
        headers: _authHeaders,
        body: jsonEncode(payload),
      ),
    );
    _ensureOk(response);
    return Customer.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<void> deleteCustomer(int customerId) async {
    final response = await _withTimeout(
      _http.delete(
        _uri('/whatsbot/customers/$customerId'),
        headers: _authHeaders,
      ),
    );
    _ensureOk(response, expected: {204, 200});
  }

  void _ensureOk(http.Response response, {Set<int>? expected}) {
    final ok = expected ?? {200};
    if (!ok.contains(response.statusCode)) {
      throw _errorFromResponse(response);
    }
  }

  ApiException _errorFromResponse(http.Response response, [String? fallback]) {
    try {
      final data = jsonDecode(response.body);
      if (data is Map && data['detail'] != null) {
        final detail = data['detail'];
        if (detail is String) {
          return ApiException(detail, statusCode: response.statusCode);
        }
        if (detail is List && detail.isNotEmpty) {
          return ApiException(
            detail.first['msg']?.toString() ?? fallback ?? 'Error',
            statusCode: response.statusCode,
          );
        }
      }
    } catch (_) {}
    return ApiException(
      fallback ?? 'Error ${response.statusCode}',
      statusCode: response.statusCode,
    );
  }
}

/// Singleton compartido en la app.
final apiClient = ApiClient();
