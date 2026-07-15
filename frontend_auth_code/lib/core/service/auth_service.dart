// lib/core/service/auth_service.dart
// All authentication API calls to Django backend

import '../constants/api_constants.dart';
import '../models/user_model.dart';
import 'dio_client.dart';
import 'storage_service.dart';
import 'package:dio/dio.dart';

class AuthService {
  final _dio     = DioClient().dio;
  final _storage = StorageService();

  // ── REGISTER ──────────────────────────────────
  // Sends name, email, password to Django
  // Returns success message or error
  Future<Map<String, dynamic>> register({
    required String name,
    required String email,
    required String password,
  }) async {
    try {
      final response = await _dio.post(
        ApiConstants.register,
        data: {
          'name':     name,
          'email':    email,
          'password': password,
        },
      );
      return {'success': true, 'message': response.data['message']};

    } on DioException catch (e) {
      return {'success': false, 'message': _handleError(e)};
    }
  }

  // ── LOGIN ─────────────────────────────────────
  // Sends email + password to Django
  // Saves tokens and returns user data
  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _dio.post(
        ApiConstants.login,
        data: {'email': email, 'password': password},
      );

      // Save both tokens securely
      await _storage.saveTokens(
        accessToken:  response.data['tokens']['access'],
        refreshToken: response.data['tokens']['refresh'],
      );

      // Return user data to UI
      final user = UserModel.fromJson(response.data['user']);
      return {'success': true, 'user': user};

    } on DioException catch (e) {
      return {'success': false, 'message': _handleError(e)};
    }
  }

  // ── PROFILE ───────────────────────────────────
  // Gets logged-in user data from Django
  // Token automatically added by Dio interceptor
  Future<Map<String, dynamic>> getProfile() async {
    try {
      final response = await _dio.get(ApiConstants.profile);
      final user = UserModel.fromJson(response.data);
      return {'success': true, 'user': user};

    } on DioException catch (e) {
      return {'success': false, 'message': _handleError(e)};
    }
  }

  // ── LOGOUT ────────────────────────────────────
  // Clears all tokens from secure storage
  Future<void> logout() async {
    await _storage.clearAll();
  }

  // ── ERROR HANDLER ─────────────────────────────
  // Converts Django error responses to user messages
  String _handleError(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.receiveTimeout:
        return 'Connection timeout — check your internet';

      case DioExceptionType.connectionError:
        return 'No internet connection';

      case DioExceptionType.badResponse:
        final status = e.response?.statusCode;
        if (status == 400) {
          // Get exact error from Django
          final errors = e.response?.data;
          if (errors is Map) {
            return errors.values.first.toString();
          }
          return 'Invalid information provided';
        }
        if (status == 401) return 'Email or password is wrong';
        if (status == 500) return 'Server error — try again later';
        return 'Something went wrong';

      default:
        return 'Unexpected error occurred';
    }
  }
}