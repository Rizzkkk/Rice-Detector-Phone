// Client-side rules that must hold regardless of what the server sends. The healthy rule and
// the applicability rule are honesty constraints, not cosmetics, so they are pinned here as
// well as in backend/test_contract.py.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rice_scanner/models.dart';
import 'package:rice_scanner/result_card.dart';

Map<String, dynamic> _body({
  String kind = 'grain',
  bool grainApplicable = true,
  bool leafApplicable = false,
  String grade = 'chalky',
  double grainConf = 0.5412,
  Map<String, double>? grainProbs,
  String disease = 'brown_spot',
  double leafConf = 0.9134,
}) =>
    {
      'subject': {'kind': kind, 'confidence': 0.9999},
      'grain': {
        'assessed': true,
        'applicable': grainApplicable,
        'grade': grade,
        'confidence': grainConf,
        'probabilities': grainProbs ??
            {'broken': 0.0181, 'chalky': 0.5412, 'stained': 0.0119, 'whole': 0.4288},
        'low_confidence': grainConf < 0.60,
      },
      'leaf': {
        'assessed': true,
        'applicable': leafApplicable,
        'disease': disease,
        'confidence': leafConf,
        'probabilities': {
          'bacterial_leaf_blight': 0.0402,
          'brown_spot': 0.9134,
          'healthy': 0.0090,
          'rice_blast': 0.0301,
          'tungro': 0.0073,
        },
        'low_confidence': false,
        'caveat': 'Recognises four rice diseases only. Cannot confirm a plant is healthy.',
      },
      'report': 'Grain: Chalky, 54% confident (low) | Leaf: not applicable to this photo',
      'image': {'width': 1280, 'height': 960},
    };

void main() {
  group('healthy is never rendered as healthy', () {
    test('the class becomes a statement about what was not found', () {
      expect(prettyDisease('healthy'), 'No recognised disease');
    });

    test('other diseases are unaffected', () {
      expect(prettyDisease('rice_blast'), 'Rice Blast');
      expect(prettyDisease('bacterial_leaf_blight'), 'Bacterial Leaf Blight');
    });

    testWidgets('the word never reaches the screen', (tester) async {
      final analysis = Analysis.fromJson(
          _body(kind: 'leaf', grainApplicable: false, leafApplicable: true, disease: 'healthy'));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResultCard(
            title: 'Leaf',
            result: analysis.leaf,
            isDisease: true,
            otherSubject: 'grain',
          ),
        ),
      ));
      expect(find.text('No recognised disease'), findsOneWidget);
      expect(find.textContaining('Healthy'), findsNothing);
    });
  });

  group('parsing', () {
    test('subject kind maps to the enum', () {
      expect(Analysis.fromJson(_body(kind: 'grain')).subject, SubjectKind.grain);
      expect(Analysis.fromJson(_body(kind: 'leaf')).subject, SubjectKind.leaf);
      expect(Analysis.fromJson(_body(kind: 'unclear')).subject, SubjectKind.unclear);
    });

    test('an unknown kind degrades to unclear, showing both results', () {
      // a future server value must never cause the app to hide the answer the user wanted
      expect(Analysis.fromJson(_body(kind: 'something_new')).subject, SubjectKind.unclear);
    });

    test('applicability is read from the server, not inferred', () {
      final a = Analysis.fromJson(_body());
      expect(a.grain.applicable, isTrue);
      expect(a.leaf.applicable, isFalse);
      // the inapplicable model is still more confident than the applicable one, which is
      // exactly why confidence cannot be used to decide this
      expect(a.leaf.confidence!, greaterThan(a.grain.confidence!));
    });
  });

  group('close call', () {
    test('shown when the top two are within 15 points', () {
      // chalky 0.5412 against whole 0.4288 is the real measured collision
      final a = Analysis.fromJson(_body());
      expect(a.grain.closeRunnerUp?.key, 'whole');
    });

    test('hidden when the winner is decisive', () {
      final a = Analysis.fromJson(_body(
        grade: 'whole',
        grainConf: 0.95,
        grainProbs: {'broken': 0.01, 'chalky': 0.03, 'stained': 0.01, 'whole': 0.95},
      ));
      expect(a.grain.closeRunnerUp, isNull);
    });
  });

  group('inapplicable result is muted, not deleted', () {
    testWidgets('it says so and does not lead with a grade', (tester) async {
      final analysis = Analysis.fromJson(_body());
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResultCard(
            title: 'Leaf',
            result: analysis.leaf,
            isDisease: true,
            otherSubject: 'grain',
          ),
        ),
      ));
      expect(find.textContaining('not applicable'), findsOneWidget);
      // the disease name is behind a tap, never presented as the answer
      expect(find.text('Brown Spot'), findsNothing);
    });
  });

  group('applicable result', () {
    testWidgets('shows the confidence number and the uncertain flag', (tester) async {
      final analysis = Analysis.fromJson(_body());
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResultCard(
            title: 'Grain',
            result: analysis.grain,
            isDisease: false,
            otherSubject: 'a leaf',
          ),
        ),
      ));
      expect(find.text('Chalky'), findsOneWidget);
      expect(find.text('54% confident'), findsOneWidget);
      expect(find.text('uncertain'), findsOneWidget);
      expect(find.textContaining('could also be Whole'), findsOneWidget);
    });

    testWidgets('renders the caveat on every leaf answer', (tester) async {
      final analysis = Analysis.fromJson(
          _body(kind: 'leaf', grainApplicable: false, leafApplicable: true));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResultCard(
            title: 'Leaf',
            result: analysis.leaf,
            isDisease: true,
            otherSubject: 'grain',
          ),
        ),
      ));
      // present even though this answer is 91% confident
      expect(find.textContaining('Cannot confirm a plant is healthy'), findsOneWidget);
    });
  });
}
