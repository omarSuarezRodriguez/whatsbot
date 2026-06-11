import 'package:flutter/material.dart';

/// Colores y estilos inspirados en WhatsApp (sin assets de Meta).
class WhatsAppTheme {
  WhatsAppTheme._();

  static const Color headerGreen = Color(0xFF075E54);
  static const Color accentGreen = Color(0xFF128C7E);
  static const Color lightGreen = Color(0xFF25D366);
  static const Color outgoingBubble = Color(0xFFDCF8C6);
  static const Color incomingBubble = Colors.white;
  static const Color chatBackground = Color(0xFFECE5DD);
  static const Color divider = Color(0xFFD1D7DB);
  static const Color subtitleGrey = Color(0xFF667781);
  static const Color unreadBadge = Color(0xFF25D366);

  static ThemeData light() {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: headerGreen,
        primary: headerGreen,
        secondary: accentGreen,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: headerGreen,
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
      ),
      scaffoldBackgroundColor: Colors.white,
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(24),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: accentGreen,
        foregroundColor: Colors.white,
      ),
      listTileTheme: const ListTileThemeData(
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      ),
    );
  }
}
