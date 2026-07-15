# 🚀 SafeSpeak - Frontend Setup Guide

Hey bro! The backend APIs and auth flow are completely ready. Before running the frontend (Flutter), please follow these quick steps to set up API integration and secure token storage:

## 🛠️ Step 1: Update pubspec.yaml
Open your `pubspec.yaml` file and add these 2 packages under the `dependencies:` section:

dependencies:
  flutter:
    sdk: flutter

  # For HTTP calls and API Interceptors
  dio: ^5.4.0

  # For saving JWT tokens securely
  flutter_secure_storage: ^9.0.0


## 📥 Step 2: Install Dependencies
Open your VS Code terminal in the project root folder and run this command:

flutter pub get


## 🏃‍♂️ Step 3: Run the System
That's it! You can now run the Flutter app. The backend is fully ready to connect with the frontend. 

Let me know if you face any issues with the API or routing. Happy coding! 💻🔥