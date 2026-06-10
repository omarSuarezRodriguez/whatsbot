import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/whatsapp_theme.dart';

/// Editor simple de intents por comando (menu, pedido, etc.).
class IntentsEditorScreen extends StatefulWidget {
  const IntentsEditorScreen({super.key});

  @override
  State<IntentsEditorScreen> createState() => _IntentsEditorScreenState();
}

class _IntentsEditorScreenState extends State<IntentsEditorScreen> {
  Map<String, dynamic> _config = {};
  bool _loading = true;
  bool _saving = false;

  static const _knownKeys = ['menu', 'pedido', 'reservar', 'inicio', 'cancelar'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final config = await apiClient.getIntents();
      if (!mounted) return;
      setState(() {
        _config = config;
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
      final saved = await apiClient.saveIntents(_config);
      if (!mounted) return;
      setState(() {
        _config = saved;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Intents guardados. El bot reconocerá las frases nuevas al instante.',
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

  Map<String, dynamic> _intentMap(String key) {
    final raw = _config[key];
    if (raw is Map<String, dynamic>) return Map<String, dynamic>.from(raw);
    if (raw is Map) return raw.map((k, v) => MapEntry(k.toString(), v));
    return {'phrases': <String>[], 'tokens': <String>[]};
  }

  List<String> _phrasesOf(String key) {
    final m = _intentMap(key);
    final p = m['phrases'];
    if (p is List) return p.map((e) => e.toString()).toList();
    return [];
  }

  List<String> _tokensOf(String key) {
    final m = _intentMap(key);
    final t = m['tokens'];
    if (t is List) return t.map((e) => e.toString()).toList();
    return [];
  }

  Future<void> _editIntent(String key) async {
    final phrasesCtrl = TextEditingController(
      text: _phrasesOf(key).join('\n'),
    );
    final tokensCtrl = TextEditingController(
      text: _tokensOf(key).join(', '),
    );

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Intent: $key'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Frases (una por línea):',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: phrasesCtrl,
                maxLines: 8,
                decoration: const InputDecoration(
                  hintText: 'ver el menu\nquiero la carta',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Palabras clave (separadas por coma):',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: tokensCtrl,
                decoration: const InputDecoration(
                  hintText: 'menu, carta, catalogo',
                  border: OutlineInputBorder(),
                ),
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
            child: const Text('Guardar'),
          ),
        ],
      ),
    );

    if (ok != true) return;

    final existing = _intentMap(key);
    setState(() {
      _config[key] = {
        ...existing,
        'phrases': phrasesCtrl.text
            .split('\n')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
        'tokens': tokensCtrl.text
            .split(',')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    final keys = {
      ..._knownKeys,
      ..._config.keys,
    }.toList()
      ..sort();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Intents'),
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
                  'Define qué escribe el cliente para activar cada flujo del bot.',
                  style: TextStyle(color: WhatsAppTheme.subtitleGrey),
                ),
                const SizedBox(height: 16),
                ...keys.map((key) {
                  final phrases = _phrasesOf(key);
                  return Card(
                    margin: const EdgeInsets.only(bottom: 10),
                    child: ListTile(
                      title: Text(key, style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: Text(
                        phrases.isEmpty
                            ? 'Sin frases configuradas'
                            : '${phrases.length} frases · ${phrases.take(2).join(", ")}',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: const Icon(Icons.edit),
                      onTap: () => _editIntent(key),
                    ),
                  );
                }),
              ],
            ),
    );
  }
}
