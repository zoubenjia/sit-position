import 'package:flutter/material.dart';
import 'package:sit_position_mobile/screens/home_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SitPositionApp());
}

class SitPositionApp extends StatelessWidget {
  const SitPositionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NeckCheck',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.blue,
        useMaterial3: true,
        brightness: Brightness.light,
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black87,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}
