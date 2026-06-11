import 'package:flutter/material.dart';

import '../models/menu_item.dart';
import '../services/api_client.dart';

class MenuEditorScreen extends StatefulWidget {
  const MenuEditorScreen({super.key});

  @override
  State<MenuEditorScreen> createState() => _MenuEditorScreenState();
}

class _MenuEditorScreenState extends State<MenuEditorScreen> {
  List<MenuItemModel> _items = [];
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final items = await apiClient.getMenu();
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final saved = await apiClient.saveMenu(_items);
      if (!mounted) return;
      setState(() {
        _items = saved;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Menú guardado. El bot usará estos productos en el próximo mensaje.',
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    }
  }

  void _addItem() {
    setState(() {
      _items.add(
        MenuItemModel(
          externalId: 'item-${DateTime.now().millisecondsSinceEpoch}',
          nombre: 'Nuevo producto',
          precio: 0,
          categoria: 'General',
          disponible: true,
        ),
      );
    });
  }

  Future<void> _editItem(int index) async {
    final item = _items[index];
    final nombreCtrl = TextEditingController(text: item.nombre);
    final precioCtrl = TextEditingController(text: item.precio.toString());
    final catCtrl = TextEditingController(text: item.categoria);
    var disponible = item.disponible;

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialog) => AlertDialog(
          title: const Text('Editar producto'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nombreCtrl,
                  decoration: const InputDecoration(labelText: 'Nombre'),
                ),
                TextField(
                  controller: precioCtrl,
                  decoration: const InputDecoration(labelText: 'Precio'),
                  keyboardType: TextInputType.number,
                ),
                TextField(
                  controller: catCtrl,
                  decoration: const InputDecoration(labelText: 'Categoría'),
                ),
                SwitchListTile(
                  title: const Text('Disponible'),
                  value: disponible,
                  onChanged: (v) => setDialog(() => disponible = v),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Aceptar'),
            ),
          ],
        ),
      ),
    );

    if (ok != true) return;
    setState(() {
      _items[index] = item.copyWith(
        nombre: nombreCtrl.text.trim(),
        precio: double.tryParse(precioCtrl.text) ?? item.precio,
        categoria: catCtrl.text.trim(),
        disponible: disponible,
      );
    });
  }

  void _removeItem(int index) {
    setState(() => _items.removeAt(index));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Menú'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.all(16),
              child: SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          else
            IconButton(
              icon: const Icon(Icons.save),
              tooltip: 'Guardar',
              onPressed: _save,
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _addItem,
        child: const Icon(Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _items.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text('No hay productos. Agrega uno con +'),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: _addItem,
                        icon: const Icon(Icons.add),
                        label: const Text('Agregar producto'),
                      ),
                    ],
                  ),
                )
              : ListView.separated(
                  itemCount: _items.length,
                  separatorBuilder: (context, index) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final item = _items[index];
                    return ListTile(
                      title: Text(item.nombre),
                      subtitle: Text(
                        '${item.categoria.isNotEmpty ? "${item.categoria} · " : ""}'
                        '\$${item.precio.toStringAsFixed(0)}'
                        '${item.disponible ? "" : " · No disponible"}',
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            icon: const Icon(Icons.edit),
                            onPressed: () => _editItem(index),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete_outline,
                                color: Colors.red),
                            onPressed: () => _removeItem(index),
                          ),
                        ],
                      ),
                      onTap: () => _editItem(index),
                    );
                  },
                ),
    );
  }
}
