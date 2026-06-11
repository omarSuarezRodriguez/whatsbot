import 'package:flutter/material.dart';

import 'di/app_services.dart';
import 'screens/login_screen.dart';
import 'screens/main_shell.dart';
import 'services/api_client.dart';
import 'services/message_alerts_service.dart';
import 'services/push_service.dart';
import 'theme/whatsapp_theme.dart';
import 'widgets/app_lifecycle_observer.dart';

final navigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppServices.init();
  await messageAlerts.init();
  await pushService.init();
  runApp(const WhatsBotApp());
}

class WhatsBotApp extends StatelessWidget {
  const WhatsBotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AppLifecycleObserver(
      child: MaterialApp(
        navigatorKey: navigatorKey,
        title: 'WhatsBot',
        debugShowCheckedModeBanner: false,
        theme: WhatsAppTheme.light(),
        home: const SplashGate(),
      ),
    );
  }
}

/// Restaura sesión JWT o muestra login.
class SplashGate extends StatefulWidget {
  const SplashGate({super.key});

  @override
  State<SplashGate> createState() => _SplashGateState();
}

class _SplashGateState extends State<SplashGate> {
  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    await apiClient.loadSession();
    if (apiClient.isLoggedIn) {
      AppServices.resetSessionFlags();
      try {
        await pushService.registerAfterLogin();
      } catch (_) {}
      try {
        await AppServices.startRealtimeSession();
      } catch (_) {}
    }
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => apiClient.isLoggedIn
            ? const MainShell()
            : const LoginScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WhatsAppTheme.headerGreen,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.chat, size: 64, color: Colors.white),
            const SizedBox(height: 16),
            Text(
              'WhatsBot',
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 24),
            const CircularProgressIndicator(color: Colors.white),
          ],
        ),
      ),
    );
  }
}
