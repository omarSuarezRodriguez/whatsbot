import 'package:flutter/material.dart';

import '../di/app_services.dart';
import '../services/api_client.dart';
import '../services/message_alerts_service.dart';
import '../services/push_service.dart';
import '../theme/whatsapp_theme.dart';
import 'chats_list_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _businessController = TextEditingController(text: 'default');
  final _pinController = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _businessController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await apiClient.login(
        _businessController.text.trim(),
        _pinController.text,
      );
      AppServices.resetSessionFlags();
      messageAlerts.seedFromLogin();
      await pushService.registerAfterLogin();
      await AppServices.startRealtimeSession();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const ChatsListScreen()),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = 'Error de conexión. ¿Está la API encendida?');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WhatsAppTheme.headerGreen,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 88,
                  height: 88,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.15),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.chat,
                    size: 48,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'WhatsBot',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Gestiona tu bot de WhatsApp',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.85),
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: 40),
                Card(
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextField(
                          controller: _businessController,
                          decoration: const InputDecoration(
                            labelText: 'ID del negocio',
                            prefixIcon: Icon(Icons.store),
                          ),
                          textInputAction: TextInputAction.next,
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _pinController,
                          decoration: const InputDecoration(
                            labelText: 'PIN del dueño',
                            prefixIcon: Icon(Icons.lock_outline),
                          ),
                          obscureText: true,
                          onSubmitted: (_) => _submit(),
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            _error!,
                            style: const TextStyle(color: Colors.red),
                          ),
                        ],
                        const SizedBox(height: 20),
                        FilledButton(
                          onPressed: _loading ? null : _submit,
                          style: FilledButton.styleFrom(
                            backgroundColor: WhatsAppTheme.accentGreen,
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                          child: _loading
                              ? const SizedBox(
                                  height: 22,
                                  width: 22,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Text('Entrar'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
