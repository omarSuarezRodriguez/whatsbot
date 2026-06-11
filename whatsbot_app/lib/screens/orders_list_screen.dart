import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/order.dart';
import '../services/api_client.dart';
import '../theme/whatsapp_theme.dart';

class OrdersListScreen extends StatefulWidget {
  const OrdersListScreen({super.key});

  @override
  State<OrdersListScreen> createState() => _OrdersListScreenState();
}

class _OrdersListScreenState extends State<OrdersListScreen> {
  List<PendingOrder> _orders = [];
  bool _loading = true;
  String? _error;
  String _filter = 'pending';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final orders = await apiClient.getPendingOrders();
      if (!mounted) return;
      setState(() { _orders = orders; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _approve(PendingOrder order) async {
    try {
      await apiClient.approveOrder(order.orderId);
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
      );
    }
  }

  Future<void> _reject(PendingOrder order) async {
    final reason = await _askReason();
    if (reason == null) return;
    try {
      await apiClient.rejectOrder(order.orderId, reason: reason);
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
      );
    }
  }

  Future<String?> _askReason() async {
    final ctrl = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Motivo de rechazo'),
        content: TextField(controller: ctrl, decoration: const InputDecoration(hintText: 'Opcional')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('Rechazar', style: TextStyle(color: Colors.red))),
        ],
      ),
    );
  }

  static String _statusLabel(String s) => switch (s) {
    'pending' => 'Pendiente',
    'confirmed' => 'Confirmado',
    'rejected' => 'Rechazado',
    _ => s,
  };

  static Color _statusColor(String s) => switch (s) {
    'pending' => Colors.orange,
    'confirmed' => Colors.green,
    'rejected' => Colors.red,
    _ => Colors.grey,
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: WhatsAppTheme.headerGreen,
        foregroundColor: Colors.white,
        title: const Text('Pedidos'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: Colors.red),
                    const SizedBox(height: 8),
                    Text(_error!),
                    const SizedBox(height: 12),
                    ElevatedButton(onPressed: _load, child: const Text('Reintentar')),
                  ],
                ))
              : _orders.isEmpty
                  ? const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.receipt_long, size: 64, color: Colors.grey),
                          SizedBox(height: 12),
                          Text('No hay pedidos pendientes', style: TextStyle(color: Colors.grey, fontSize: 16)),
                        ],
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(8),
                      itemCount: _orders.length,
                      itemBuilder: (_, i) => _OrderCard(
                        order: _orders[i],
                        onApprove: () => _approve(_orders[i]),
                        onReject: () => _reject(_orders[i]),
                        statusLabel: _statusLabel,
                        statusColor: _statusColor,
                      ),
                    ),
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({
    required this.order,
    required this.onApprove,
    required this.onReject,
    required this.statusLabel,
    required this.statusColor,
  });

  final PendingOrder order;
  final VoidCallback onApprove;
  final VoidCallback onReject;
  final String Function(String) statusLabel;
  final Color Function(String) statusColor;

  static final _fmt = DateFormat('dd/MM/yyyy HH:mm');

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    order.orderId,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: statusColor(order.status).withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    statusLabel(order.status),
                    style: TextStyle(color: statusColor(order.status), fontWeight: FontWeight.w600, fontSize: 12),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            if (order.customerName.isNotEmpty)
              _InfoRow(Icons.person, order.customerName),
            _InfoRow(Icons.phone, order.waId),
            if (order.address.isNotEmpty)
              _InfoRow(Icons.location_on, order.address),
            const SizedBox(height: 8),
            ...order.items.map((item) => Padding(
              padding: const EdgeInsets.only(left: 8, bottom: 2),
              child: Text(
                '• ${item['nombre'] ?? item['name'] ?? ''} × ${item['qty'] ?? item['quantity'] ?? 1} — \$${item['precio'] ?? item['price'] ?? 0}',
                style: const TextStyle(fontSize: 13),
              ),
            )),
            const SizedBox(height: 8),
            Row(
              children: [
                Text('\$${order.total.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                const Spacer(),
                Text(_fmt.format(order.createdAt.toLocal()), style: const TextStyle(color: Colors.grey, fontSize: 12)),
              ],
            ),
            if (order.status == 'pending') ...[
              const Divider(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  OutlinedButton.icon(
                    onPressed: onReject,
                    icon: const Icon(Icons.close, color: Colors.red),
                    label: const Text('Rechazar', style: TextStyle(color: Colors.red)),
                    style: OutlinedButton.styleFrom(side: const BorderSide(color: Colors.red)),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton.icon(
                    onPressed: onApprove,
                    icon: const Icon(Icons.check),
                    label: const Text('Aprobar'),
                    style: ElevatedButton.styleFrom(backgroundColor: WhatsAppTheme.headerGreen, foregroundColor: Colors.white),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.icon, this.text);
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        children: [
          Icon(icon, size: 14, color: Colors.grey),
          const SizedBox(width: 6),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}
