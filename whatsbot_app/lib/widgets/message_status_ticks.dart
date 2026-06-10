import 'package:flutter/material.dart';

import '../models/message.dart';
import '../theme/whatsapp_theme.dart';

/// Checks estilo WhatsApp en mensajes salientes del dueño.
class MessageStatusTicks extends StatelessWidget {
  const MessageStatusTicks({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    if (!message.isOutgoing || !message.isAdmin) {
      return const SizedBox.shrink();
    }

    final Color color;
    final IconData icon;
    switch (message.status) {
      case 'read':
        color = const Color(0xFF34B7F1);
        icon = Icons.done_all;
      case 'delivered':
        color = WhatsAppTheme.subtitleGrey.withValues(alpha: 0.85);
        icon = Icons.done_all;
      case 'sent':
        color = WhatsAppTheme.subtitleGrey.withValues(alpha: 0.85);
        icon = Icons.done;
      case 'pending':
        color = WhatsAppTheme.subtitleGrey.withValues(alpha: 0.6);
        icon = Icons.schedule;
      default:
        color = WhatsAppTheme.subtitleGrey.withValues(alpha: 0.6);
        icon = Icons.access_time;
    }

    return Icon(icon, size: 14, color: color);
  }
}
