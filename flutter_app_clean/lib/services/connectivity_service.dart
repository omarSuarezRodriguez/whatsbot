import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

/// Detecta red disponible y dispara sync al volver online (OF-D).
class ConnectivityService {
  ConnectivityService._();

  static final ConnectivityService instance = ConnectivityService._();

  final Connectivity _connectivity = Connectivity();
  final StreamController<bool> _onlineState =
      StreamController<bool>.broadcast();

  StreamSubscription<List<ConnectivityResult>>? _subscription;
  Future<void> Function()? onBackOnline;
  bool _online = true;
  bool _started = false;

  Stream<bool> get onlineState => _onlineState.stream;

  bool get isOnline => _online;

  Future<void> start() async {
    if (_started) return;
    _started = true;

    final initial = await _connectivity.checkConnectivity();
    _setOnline(_hasNetwork(initial));

    _subscription = _connectivity.onConnectivityChanged.listen((results) {
      final wasOnline = _online;
      _setOnline(_hasNetwork(results));
      if (!wasOnline && _online) {
        unawaited(onBackOnline?.call());
      }
    });
  }

  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
    _started = false;
  }

  void _setOnline(bool value) {
    if (_online == value) return;
    _online = value;
    _onlineState.add(value);
  }

  bool _hasNetwork(List<ConnectivityResult> results) {
    return results.any(
      (result) =>
          result == ConnectivityResult.mobile ||
          result == ConnectivityResult.wifi ||
          result == ConnectivityResult.ethernet ||
          result == ConnectivityResult.vpn,
    );
  }
}

final connectivityService = ConnectivityService.instance;
