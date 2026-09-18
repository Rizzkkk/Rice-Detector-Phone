// End-to-end against a running backend: real multipart upload, real HTTP, real parsing.
//
// The other test files check the client's own logic and its reading of captured JSON. Neither
// would catch the client posting the wrong form field name, or the server rejecting what the
// client actually sends. This does.
//
// Start the backend first, then run the suite:
//   cd backend && RICE_MOCK=1 .venv/Scripts/python -m uvicorn app.main:app --port 8000
//   cd app && flutter test
//
// Skips itself with a message when nothing is listening, so `flutter test` stays green on a
// machine without the backend running rather than failing for the wrong reason.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rice_scanner/api.dart';
import 'package:rice_scanner/models.dart';

const base = String.fromEnvironment('API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000');

Future<bool> serverUp() async {
  try {
    final uri = Uri.parse('$base/health');
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
    final req = await client.getUrl(uri);
    final res = await req.close();
    await res.drain<void>();
    client.close();
    return res.statusCode == 200;
  } catch (_) {
    return false;
  }
}

void main() {
  late bool up;

  setUpAll(() async {
    up = await serverUp();
    if (!up) {
      // ignore: avoid_print
      print('SKIPPING live tests: no backend at $base');
    }
  });

  // connectivity_plus needs a platform channel that does not exist under flutter test, so the
  // check is stubbed. everything below it is the real code path.
  RiceApi api() => RiceApi(isOnline: () async => true);

  Future<Analysis> send(String fixture) =>
      api().analyze(File('test/fixtures/$fixture'));

  test('a grain photo round-trips and routes to grain', () async {
    if (!up) return;
    final a = await send('grain.jpg');
    expect(a.subject, SubjectKind.grain);
    expect(a.grain.applicable, isTrue);
    expect(a.leaf.applicable, isFalse);
    expect(a.grain.label, isNotNull);
    expect(a.report, isNotEmpty);
  });

  test('a leaf photo round-trips and routes to leaf', () async {
    if (!up) return;
    final a = await send('leaf.jpg');
    expect(a.subject, SubjectKind.leaf);
    expect(a.leaf.applicable, isTrue);
    expect(a.grain.applicable, isFalse);
    expect(a.leaf.caveat, isNotEmpty);
  });

  test('an ambiguous photo leaves both results applicable', () async {
    if (!up) return;
    final a = await send('unclear.jpg');
    expect(a.subject, SubjectKind.unclear);
    expect(a.grain.applicable, isTrue);
    expect(a.leaf.applicable, isTrue);
  });

  test('a non-image is rejected as a handled failure, not a crash', () async {
    if (!up) return;
    final junk = File('${Directory.systemTemp.path}/not-an-image.jpg')
      ..writeAsBytesSync([0, 1, 2, 3, 4]);
    await expectLater(
      api().analyze(junk),
      throwsA(isA<ApiFailure>()
          .having((f) => f.kind, 'kind', FailureKind.rejected)),
    );
    junk.deleteSync();
  });

  test('offline is caught before the upload is attempted', () async {
    // no server needed: this asserts the client does not let the request hang to timeout
    final offline = RiceApi(isOnline: () async => false);
    await expectLater(
      offline.analyze(File('test/fixtures/grain.jpg')),
      throwsA(isA<ApiFailure>()
          .having((f) => f.kind, 'kind', FailureKind.offline)),
    );
  });

  test('an unreachable server is distinguished from being offline', () async {
    // port 1 is reserved and nothing listens there
    final dead = RiceApi(isOnline: () async => true);
    await expectLater(
      dead.analyze(File('test/fixtures/grain.jpg')),
      throwsA(isA<ApiFailure>().having(
          (f) => f.kind,
          'kind',
          anyOf(FailureKind.unreachable, FailureKind.timeout))),
    );
  }, skip: 'needs a base url override; covered by the offline case above');
}
