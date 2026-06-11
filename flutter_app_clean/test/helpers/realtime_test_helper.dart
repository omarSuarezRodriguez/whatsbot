import 'package:whatsbot_app/models/realtime_event.dart';
import 'package:whatsbot_app/services/realtime_service.dart';

/// Emite un evento WS tipado sin backend: persiste vía SyncEngine y notifica UI.
Future<void> emitRealtimeEvent(RealtimeEvent event) =>
    realtimeService.debugEmitEvent(event);
