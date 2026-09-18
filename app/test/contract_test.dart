// Parses responses captured from the running backend, not hand-written ones.
//
// The client and the server were each written against docs/02-api-contract.md rather than
// against each other, which is the point - but it means nothing actually checks that the two
// readings agree. These fixtures come from backend/test_contract.py's mock mode, so a field
// renamed on one side fails here instead of on a phone at a mill.
//
// Regenerate after any contract change; the backend README says how.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rice_scanner/models.dart';

Analysis load(String name) {
  final file = File('test/fixtures/$name.json');
  return Analysis.fromJson(
      jsonDecode(file.readAsStringSync()) as Map<String, dynamic>);
}

void main() {
  test('a grain photo routes to grain and mutes leaf', () {
    final a = load('grain');
    expect(a.subject, SubjectKind.grain);
    expect(a.grain.applicable, isTrue);
    expect(a.leaf.applicable, isFalse);
    expect(a.grain.label, 'chalky');
    expect(a.report, startsWith('Grain:'));
  });

  test('a leaf photo routes to leaf and mutes grain', () {
    final a = load('leaf');
    expect(a.subject, SubjectKind.leaf);
    expect(a.leaf.applicable, isTrue);
    expect(a.grain.applicable, isFalse);
    expect(a.leaf.label, 'brown_spot');
    expect(a.report, startsWith('Leaf:'));
  });

  test('an unclear photo leaves both applicable', () {
    final a = load('unclear');
    expect(a.subject, SubjectKind.unclear);
    expect(a.grain.applicable, isTrue);
    expect(a.leaf.applicable, isTrue);
  });

  test('never both inapplicable, in any fixture', () {
    for (final name in ['grain', 'leaf', 'unclear']) {
      final a = load(name);
      expect(a.grain.applicable || a.leaf.applicable, isTrue,
          reason: '$name left the user with no result at all');
    }
  });

  test('probabilities survive the round trip and sum to one', () {
    for (final name in ['grain', 'leaf', 'unclear']) {
      final a = load(name);
      for (final r in [a.grain, a.leaf]) {
        expect(r.probabilities, isNotEmpty);
        final total = r.probabilities.values.fold<double>(0, (s, v) => s + v);
        expect(total, closeTo(1.0, 0.01));
        // whatever the server called the winner must be the largest score, or the card
        // would show one label next to another label's bar
        final top = r.probabilities.entries
            .reduce((a, b) => a.value >= b.value ? a : b);
        expect(top.key, r.label);
      }
    }
  });

  test('the leaf caveat is present on every response', () {
    for (final name in ['grain', 'leaf', 'unclear']) {
      final a = load(name);
      expect(a.leaf.caveat, isNotNull, reason: name);
      expect(a.leaf.caveat, isNotEmpty, reason: name);
    }
  });

  test('the measured chalky-whole collision is flagged as a close call', () {
    final a = load('grain');
    expect(a.grain.closeRunnerUp?.key, 'whole');
  });

  test('low confidence survives as a flag, not just as prose in the report', () {
    final a = load('grain');
    expect(a.grain.lowConfidence, isTrue);
    expect(a.report, contains('(low)'));
  });
}
