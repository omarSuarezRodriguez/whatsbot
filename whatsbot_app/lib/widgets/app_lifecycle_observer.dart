import 'dart:async' show unawaited;

import 'package:flutter/widgets.dart';

import '../di/app_services.dart';
import '../services/message_alerts_service.dart';

/// Propaga ciclo de vida: primer plano → reconectar WS + sync (estilo WhatsApp).
class AppLifecycleObserver extends StatefulWidget {
  const AppLifecycleObserver({super.key, required this.child});

  final Widget child;

  @override
  State<AppLifecycleObserver> createState() => _AppLifecycleObserverState();
}

class _AppLifecycleObserverState extends State<AppLifecycleObserver>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    messageAlerts.setAppInForeground(true);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        messageAlerts.setAppInForeground(true);
        unawaited(AppServices.onAppResumed());
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        messageAlerts.setAppInForeground(false);
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
