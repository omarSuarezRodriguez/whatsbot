import 'package:flutter/material.dart';

import '../models/order.dart';
import '../theme/whatsapp_theme.dart';

/// Barra de aprobar / rechazar pedido pendiente del cliente en el chat.
class OrderActionsBar extends StatelessWidget {
  const OrderActionsBar({
    super.key,
    required this.order,
    required this.onApprove,
    required this.onReject,
    this.busy = false,
  });

  final PendingOrder order;
  final VoidCallback onApprove;
  final VoidCallback onReject;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final itemsSummary = order.items
        .map((i) => i['nombre'] ?? i['name'] ?? '')
        .where((s) => s.toString().isNotEmpty)
        .take(3)
        .join(', ');

    return Material(
      color: const Color(0xFFFFF8E1),
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.receipt_long, color: WhatsAppTheme.headerGreen),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Pedido ${order.orderId}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                    ),
                  ),
                ),
                Text(
                  '\$${order.total.toStringAsFixed(0)}',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            if (itemsSummary.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                itemsSummary,
                style: TextStyle(
                  fontSize: 13,
                  color: WhatsAppTheme.subtitleGrey,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: busy ? null : onReject,
                    icon: const Icon(Icons.close, color: Colors.red),
                    label: const Text('Rechazar'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.red,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: busy ? null : onApprove,
                    icon: busy
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.check),
                    label: const Text('Aprobar'),
                    style: FilledButton.styleFrom(
                      backgroundColor: WhatsAppTheme.accentGreen,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
