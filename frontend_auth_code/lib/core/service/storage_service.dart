// lib/core/service/storage_service.dart
// Handles secure token storage on device

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class StorageService {
  // Singleton — only one instance in whole app
  static final StorageService _instance = StorageService._internal();
  factory StorageService() => _instance;
  StorageService._internal();

  final _storage = const FlutterSecureStorage();

  // Storage keys
  static const String _accessKey  = 'access_token';
  static const String _refreshKey = 'refresh_token';

  // Save both tokens after login
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessKey,  value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  // Read access token for API calls
  Future<String?> getAccessToken() async {
    return await _storage.read(key: _accessKey);
  }

  // Read refresh token when access expires
  Future<String?> getRefreshToken() async {
    return await _storage.read(key: _refreshKey);
  }

  // Delete all tokens on logout
  Future<void> clearAll() async {
    await _storage.deleteAll();
  }

  // Check if user is already logged in
  Future<bool> isLoggedIn() async {
    final token = await getAccessToken();
    return token != null;
  }
}