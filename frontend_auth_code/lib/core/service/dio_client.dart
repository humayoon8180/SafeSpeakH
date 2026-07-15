// lib/core/service/dio_client.dart
// Dio HTTP client with automatic token injection

import 'package:dio/dio.dart';
import '../constants/api_constants.dart';
import 'storage_service.dart';

class DioClient {
  // Singleton
  static final DioClient _instance = DioClient._internal();
  factory DioClient() => _instance;
  DioClient._internal();

  final StorageService _storage = StorageService();

  late final Dio dio = Dio(
    BaseOptions(
      baseUrl:        ApiConstants.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      headers: {'Content-Type': 'application/json'},
    ),
  )..interceptors.add(
    InterceptorsWrapper(
      // Before every request — add token automatically
      onRequest: (options, handler) async {
        final token = await _storage.getAccessToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },

      // On successful response — pass through
      onResponse: (response, handler) {
        return handler.next(response);
      },

      // On error — handle 401 token expired
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Token expired — try refresh
          final refreshed = await _tryRefreshToken();
          if (refreshed) {
            // Retry original request with new token
            final token = await _storage.getAccessToken();
            error.requestOptions.headers['Authorization'] 
                = 'Bearer $token';
            final response = await dio.fetch(error.requestOptions);
            return handler.resolve(response);
          } else {
            // Refresh also failed — clear tokens
            await _storage.clearAll();
          }
        }
        return handler.next(error);
      },
    ),
  );

  // Try to get new access token using refresh token
  Future<bool> _tryRefreshToken() async {
    try {
      final refreshToken = await _storage.getRefreshToken();
      if (refreshToken == null) return false;

      final response = await Dio().post(
        '${ApiConstants.baseUrl}/token/refresh/',
        data: {'refresh': refreshToken},
      );

      final newAccessToken = response.data['access'];
      final currentRefresh = await _storage.getRefreshToken();

      await _storage.saveTokens(
        accessToken:  newAccessToken,
        refreshToken: currentRefresh ?? refreshToken,
      );
      return true;
    } catch (e) {
      return false;
    }
  }
}