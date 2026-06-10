import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/whatsapp_theme.dart';

/// Editor de textos del bot (prompts) — bienvenida, errores, flujos.
class PromptsEditorScreen extends StatefulWidget {
  const PromptsEditorScreen({super.key});

  @override
  State<PromptsEditorScreen> createState() => _PromptsEditorScreenState();
}

class _PromptsEditorScreenState extends State<PromptsEditorScreen> {
  Map<String, String> _prompts = {};
  bool _loading = true;
  bool _saving = false;

  /// Claves más usadas por el dueño; el resto aparece en "Ver todos".
  static const _priorityKeys = [
    'empty_body_hint',
    'node_start_message',
    'welcome_secondary',
    'node_order_start_message',
    'node_order_saved_after',
    'error_generic',
    'cancel_message',
  ];

  static const _labels = {
    'empty_body_hint': 'Mensaje cuando el cliente envía texto vacío',
    'node_start_message': 'Mensaje de bienvenida (inicio)',
    'welcome_secondary': 'Opciones después de bienvenida',
    'node_order_start_message': 'Inicio del flujo de pedido',
    'node_order_saved_after': 'Pedido registrado (pendiente)',
    'error_generic': 'Error genérico del bot',
    'cancel_message': 'Cuando el cliente cancela',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final prompts = await apiClient.getPrompts();
      if (!mounted) return;
      setState(() {
        _prompts = prompts;
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
      final saved = await apiClient.savePrompts(_prompts);
      if (!mounted) return;
      setState(() {
        _prompts = saved;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Mensajes guardados. El próximo cliente verá los textos nuevos.',
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

  Future<void> _editPrompt(String key) async {
    final ctrl = TextEditingController(text: _prompts[key] ?? '');
    final label = _labels[key] ?? key;

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(label),
        content: SizedBox(
          width: double.maxFinite,
          child: TextField(
            controller: ctrl,
            maxLines: 10,
            decoration: InputDecoration(
              hintText: key,
              border: const OutlineInputBorder(),
            ),
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
    );

    if (ok != true) return;
    setState(() => _prompts[key] = ctrl.text);
  }

  @override
  Widget build(BuildContext context) {
    final priority = _priorityKeys.where((k) => _prompts.containsKey(k)).toList();
    final others = _prompts.keys
        .where((k) => !_priorityKeys.contains(k))
        .toList()
      ..sort();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mensajes del bot'),
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
              onPressed: _save,
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const Text(
                  'Personaliza lo que el bot le dice a tus clientes por WhatsApp.',
                  style: TextStyle(color: WhatsAppTheme.subtitleGrey),
                ),
                const SizedBox(height: 16),
                ...priority.map((key) => _promptTile(key)),
                if (others.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  const Text(
                    'Otros mensajes',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: WhatsAppTheme.subtitleGrey,
                    ),
                  ),
                  ...others.map((key) => _promptTile(key)),
                ],
              ],
            ),
    );
  }

  Widget _promptTile(String key) {
    final label = _labels[key] ?? key;
    final preview = (_prompts[key] ?? '').replaceAll('\n', ' ');
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        title: Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
        subtitle: Text(
          preview.isEmpty ? '(vacío)' : preview,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: const Icon(Icons.edit),
        onTap: () => _editPrompt(key),
      ),
    );
  }
}
