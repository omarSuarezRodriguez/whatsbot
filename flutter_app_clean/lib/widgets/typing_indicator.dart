import 'package:flutter/material.dart';

import '../theme/whatsapp_theme.dart';

class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: WhatsAppTheme.incomingBubble,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Text(
            'escribiendo…',
            style: TextStyle(
              fontSize: 13,
              fontStyle: FontStyle.italic,
              color: WhatsAppTheme.subtitleGrey,
            ),
          ),
        ),
      ),
    );
  }
}
