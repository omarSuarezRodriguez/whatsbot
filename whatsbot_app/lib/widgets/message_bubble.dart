import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/message.dart';
import '../theme/whatsapp_theme.dart';
import 'message_status_ticks.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final outgoing = message.isOutgoing;
    final isBotReply = outgoing && !message.isAdmin;
    final time = DateFormat('HH:mm').format(message.createdAt.toLocal());

    return Align(
      alignment: outgoing ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        padding: const EdgeInsets.fromLTRB(10, 6, 10, 4),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.78,
        ),
        decoration: BoxDecoration(
          color: outgoing
              ? (isBotReply
                  ? const Color(0xFFE7F6E1)
                  : WhatsAppTheme.outgoingBubble)
              : WhatsAppTheme.incomingBubble,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(8),
            topRight: const Radius.circular(8),
            bottomLeft: Radius.circular(outgoing ? 8 : 0),
            bottomRight: Radius.circular(outgoing ? 0 : 8),
          ),
          boxShadow: const [
            BoxShadow(
              color: Color(0x1A000000),
              blurRadius: 1,
              offset: Offset(0, 1),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (isBotReply) ...[
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'WhatsBot',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: WhatsAppTheme.accentGreen.withValues(alpha: 0.9),
                  ),
                ),
              ),
              const SizedBox(height: 2),
            ],
            Text(
              message.body,
              style: const TextStyle(fontSize: 15, height: 1.35),
            ),
            const SizedBox(height: 2),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  time,
                  style: TextStyle(
                    fontSize: 11,
                    color: WhatsAppTheme.subtitleGrey.withValues(alpha: 0.9),
                  ),
                ),
                if (outgoing) ...[
                  const SizedBox(width: 4),
                  MessageStatusTicks(message: message),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}
