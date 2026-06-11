import 'dart:async';

import 'package:flutter/material.dart';

import '../models/customer.dart';
import '../services/api_client.dart';
import '../theme/whatsapp_theme.dart';
import 'customer_editor_screen.dart';

class CustomersListScreen extends StatefulWidget {
  const CustomersListScreen({super.key});

  @override
  State<CustomersListScreen> createState() => _CustomersListScreenState();
}

class _CustomersListScreenState extends State<CustomersListScreen> {
  List<Customer> _customers = [];
  bool _loading = true;
  String? _error;
  final _searchCtrl = TextEditingController();
  Timer? _searchDebounce;

  @override
  void initState() {
    super.initState();
    _load();
    _searchCtrl.addListener(_onSearchChanged);
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _searchDebounce?.cancel();
    super.dispose();
  }

  void _onSearchChanged() {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 350), () => _load(search: _searchCtrl.text.trim()));
  }

  Future<void> _load({String? search}) async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final list = await apiClient.getCustomers(search: search?.isEmpty == true ? null : search);
      if (!mounted) return;
      setState(() { _customers = list; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _openEditor([Customer? customer]) async {
    final result = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CustomerEditorScreen(customer: customer),
      ),
    );
    if (result == true) _load(search: _searchCtrl.text.trim());
  }

  Future<void> _delete(Customer customer) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Eliminar cliente'),
        content: Text('¿Eliminar a ${customer.displayName}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Eliminar', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirm != true) return;
    try {
      await apiClient.deleteCustomer(customer.id);
      _load(search: _searchCtrl.text.trim());
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: WhatsAppTheme.headerGreen,
        foregroundColor: Colors.white,
        title: const Text('Clientes'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _load(search: _searchCtrl.text.trim()),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: TextField(
              controller: _searchCtrl,
              style: const TextStyle(color: Colors.white),
              cursorColor: Colors.white,
              decoration: InputDecoration(
                hintText: 'Buscar por nombre o WhatsApp…',
                hintStyle: const TextStyle(color: Colors.white70),
                prefixIcon: const Icon(Icons.search, color: Colors.white70),
                filled: true,
                fillColor: Colors.white.withOpacity(0.15),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(vertical: 8),
              ),
            ),
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _openEditor(),
        backgroundColor: WhatsAppTheme.headerGreen,
        foregroundColor: Colors.white,
        child: const Icon(Icons.person_add),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 8),
            Text(_error!, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _load, child: const Text('Reintentar')),
          ],
        ),
      );
    }
    if (_customers.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.people_outline, size: 64, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('No hay clientes aún', style: TextStyle(color: Colors.grey, fontSize: 16)),
            const SizedBox(height: 8),
            ElevatedButton.icon(
              onPressed: () => _openEditor(),
              icon: const Icon(Icons.person_add),
              label: const Text('Agregar cliente'),
              style: ElevatedButton.styleFrom(backgroundColor: WhatsAppTheme.headerGreen, foregroundColor: Colors.white),
            ),
          ],
        ),
      );
    }
    return ListView.builder(
      itemCount: _customers.length,
      itemBuilder: (_, i) => _CustomerTile(
        customer: _customers[i],
        onTap: () => _openEditor(_customers[i]),
        onDelete: () => _delete(_customers[i]),
      ),
    );
  }
}

class _CustomerTile extends StatelessWidget {
  const _CustomerTile({
    required this.customer,
    required this.onTap,
    required this.onDelete,
  });

  final Customer customer;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: customer.blocked ? Colors.red.shade100 : WhatsAppTheme.headerGreen.withOpacity(0.15),
        child: Text(
          customer.displayName.substring(0, 1).toUpperCase(),
          style: TextStyle(
            color: customer.blocked ? Colors.red : WhatsAppTheme.headerGreen,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      title: Row(
        children: [
          Expanded(child: Text(customer.displayName, style: const TextStyle(fontWeight: FontWeight.w600))),
          if (customer.blocked)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(color: Colors.red.shade100, borderRadius: BorderRadius.circular(4)),
              child: const Text('Bloqueado', style: TextStyle(color: Colors.red, fontSize: 11)),
            ),
        ],
      ),
      subtitle: Text(customer.waId, style: const TextStyle(color: Colors.grey)),
      trailing: IconButton(
        icon: const Icon(Icons.delete_outline, color: Colors.grey),
        onPressed: onDelete,
      ),
      onTap: onTap,
    );
  }
}
