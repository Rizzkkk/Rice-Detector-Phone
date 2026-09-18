import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;

import 'models.dart';

/// The ways a request can fail, split up so the screen can word each one differently. No
/// connection and server unreachable look the same to the code but mean different things to
/// the person holding the phone. One is their problem, the other is ours.
enum FailureKind {
  offline,
  unreachable,
  starting,
  rateLimited,
  rejected,
  unauthorized,
  server,
  timeout,
}

class ApiFailure implements Exception {
  const ApiFailure(this.kind, this.message);
  final FailureKind kind;
  final String message;

  @override
  String toString() => message;
}

class RiceApi {
  RiceApi({http.Client? client, Future<bool> Function()? isOnline})
      : _client = client ?? http.Client(),
        _isOnline = isOnline ?? _platformIsOnline;

  final http.Client _client;

  /// Passed in so the end to end test can run without the connectivity plugin. That plugin
  /// needs a real device channel and there is none under flutter test.
  final Future<bool> Function() _isOnline;

  static Future<bool> _platformIsOnline() async {
    final conn = await Connectivity().checkConnectivity();
    return !conn.every((r) => r == ConnectivityResult.none);
  }

  /// Set at build time, never hardcoded. The emulator reaches the host machine at 10.0.2.2,
  /// localhost on the emulator is the emulator itself.
  static const baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Compiled in at build time like the base url. Anyone with the apk can pull it out, so it
  /// does nothing against someone who is trying. It keeps random scanners off an endpoint
  /// where every request costs the server real cpu. Empty means we send no header.
  static const apiKey = String.fromEnvironment('API_KEY');

  /// Three models run per request on a 2 core box, so this is set long on purpose. Too short
  /// and a slow server that is working fine looks broken.
  static const _timeout = Duration(seconds: 45);

  Future<Analysis> analyze(File image) async {
    // checked before uploading instead of letting it hang until it times out. there is no
    // model on the phone, so offline is a dead end and we should just say so
    if (!await _isOnline()) {
      throw const ApiFailure(
        FailureKind.offline,
        'No internet connection. Analysis runs on the server, so the app needs a connection.',
      );
    }

    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/analyze'))
      ..files.add(await http.MultipartFile.fromPath('image', image.path));
    if (apiKey.isNotEmpty) {
      request.headers['x-api-key'] = apiKey;
    }

    http.Response response;
    try {
      final streamed = await _client.send(request).timeout(_timeout);
      response = await http.Response.fromStream(streamed);
    } on SocketException {
      throw const ApiFailure(
        FailureKind.unreachable,
        'Could not reach the server. It may be offline or restarting.',
      );
    } on HttpException {
      throw const ApiFailure(
        FailureKind.unreachable,
        'Could not reach the server. It may be offline or restarting.',
      );
    } catch (_) {
      throw const ApiFailure(
        FailureKind.timeout,
        'The server took too long to respond. Try again.',
      );
    }

    if (response.statusCode == 200) {
      return Analysis.fromJson(
          jsonDecode(response.body) as Map<String, dynamic>);
    }

    // every error uses the same shape, {"error": "..."}, but never assume there is a body.
    // a proxy or a crash can send back html
    String serverMessage = '';
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map && decoded['error'] is String) {
        serverMessage = decoded['error'] as String;
      }
    } catch (_) {}

    switch (response.statusCode) {
      case 503:
        throw const ApiFailure(
          FailureKind.starting,
          'The service is starting up. Give it a moment and try again.',
        );
      case 429:
        throw const ApiFailure(
          FailureKind.rateLimited,
          'Too many photos too quickly. Wait a moment, then try again.',
        );
      case 401:
      case 403:
        // this is a build problem, not a user one. the key is compiled in so the person
        // holding the phone can do nothing about it. worded so it does not sound like the
        // server is down.
        throw const ApiFailure(
          FailureKind.unauthorized,
          'This copy of the app was not accepted by the server. It may need a newer build.',
        );
      case 400:
      case 413:
      case 415:
        // the app shrinks the photo and only sends jpeg, so getting here means the app has a
        // bug. the server's message is specific and useful so we show it instead of our own.
        throw ApiFailure(
          FailureKind.rejected,
          serverMessage.isEmpty ? 'That photo was rejected.' : serverMessage,
        );
      default:
        // never show a 5xx body. the server keeps it vague on purpose and it says nothing a
        // user could act on
        throw const ApiFailure(
          FailureKind.server,
          'Something went wrong on the server. Try again.',
        );
    }
  }

  void close() => _client.close();
}
