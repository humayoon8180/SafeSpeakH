// lib/core/models/user_model.dart
// Converts Django JSON response to Flutter object

class UserModel {
  final int    id;
  final String name;
  final String email;

  UserModel({
    required this.id,
    required this.name,
    required this.email,
  });

  // Convert JSON from Django to UserModel
  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id:    json['id'],
      name:  json['name'],
      email: json['email'],
    );
  }
}