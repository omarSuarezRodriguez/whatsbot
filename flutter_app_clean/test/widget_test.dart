import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:whatsbot_app/screens/login_screen.dart';

void main() {
  testWidgets('LoginScreen muestra WhatsBot', (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: LoginScreen()),
    );
    expect(find.text('WhatsBot'), findsOneWidget);
  });
}
