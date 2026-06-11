import 'package:flutter/material.dart';

import '../di/app_services.dart';
import '../models/business.dart';
import '../services/api_client.dart';
import '../services/push_service.dart';
import '../services/realtime_service.dart';
import '../theme/whatsapp_theme.dart';
import 'intents_editor_screen.dart';
import 'login_screen.dart';
import 'menu_editor_screen.dart';
import 'prompts_editor_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  BusinessProfile? _profile;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final profile = await apiClient.getBusinessMe();
      if (!mounted) return;
      setState(() {
        _profile = profile;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    AppServices.resetSessionFlags();
    await realtimeService.disconnect();
    await pushService.unregisterOnLogout();
    await AppServices.clearLocalData();
    await apiClient.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ajustes')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              children: [
                if (_profile != null) ...[
                  ListTile(
                    leading: const CircleAvatar(
                      backgroundColor: WhatsAppTheme.headerGreen,
                      child: Icon(Icons.store, color: Colors.white),
                    ),
                    title: Text(
                      _profile!.name,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    subtitle: Text('Negocio: ${_profile!.id}'),
                  ),
                  const Divider(),
                ],
                const Padding(
                  padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: Text(
                    'Configuración del bot',
                    style: TextStyle(
                      color: WhatsAppTheme.subtitleGrey,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                ListTile(
                  leading: const Icon(Icons.restaurant_menu,
                      color: WhatsAppTheme.accentGreen),
                  title: const Text('Menú'),
                  subtitle: const Text('Productos, precios y categorías'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => const MenuEditorScreen(),
                      ),
                    );
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.psychology_alt_outlined,
                      color: WhatsAppTheme.accentGreen),
                  title: const Text('Intents'),
                  subtitle: const Text('Palabras que activan cada flujo'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => const IntentsEditorScreen(),
                      ),
                    );
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.message_outlined,
                      color: WhatsAppTheme.accentGreen),
                  title: const Text('Mensajes'),
                  subtitle: const Text('Bienvenida, errores y textos del bot'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => const PromptsEditorScreen(),
                      ),
                    );
                  },
                ),
                const Divider(),
                ListTile(
                  leading: const Icon(Icons.logout, color: Colors.red),
                  title: const Text('Cerrar sesión'),
                  onTap: _logout,
                ),
              ],
            ),
    );
  }
}
