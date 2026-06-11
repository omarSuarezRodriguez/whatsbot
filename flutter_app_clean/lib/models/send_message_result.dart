import 'message.dart';

/// Resultado de envío: mensaje local y si quedó en cola offline.
class SendMessageResult {
  const SendMessageResult({
    required this.message,
    required this.queued,
  });

  final ChatMessage message;
  final bool queued;
}
