/// The parsed /analyze response. Written against the api contract, not against the server
/// code, so the two sides can be checked against each other.
library;

/// One model's answer.
///
/// applicable is what decides if this can be shown as a result. You cannot work it out from
/// confidence. An answer that does not apply comes back just as confident as a real one,
/// because neither model can refuse an image it was not trained for.
class ModelResult {
  const ModelResult({
    required this.assessed,
    required this.applicable,
    required this.label,
    required this.confidence,
    required this.probabilities,
    required this.lowConfidence,
    this.caveat,
  });

  final bool assessed;
  final bool applicable;
  final String? label;
  final double? confidence;
  final Map<String, double> probabilities;
  final bool lowConfidence;
  final String? caveat;

  factory ModelResult.fromJson(Map<String, dynamic> json, String labelKey) {
    final probs = <String, double>{};
    final raw = json['probabilities'];
    if (raw is Map) {
      raw.forEach((k, v) {
        if (v is num) probs['$k'] = v.toDouble();
      });
    }
    return ModelResult(
      assessed: json['assessed'] == true,
      applicable: json['applicable'] == true,
      label: json[labelKey] as String?,
      confidence: (json['confidence'] as num?)?.toDouble(),
      probabilities: probs,
      lowConfidence: json['low_confidence'] == true,
      caveat: json['caveat'] as String?,
    );
  }

  /// The rest of the classes, best first, without the winner.
  List<MapEntry<String, double>> get others {
    final entries = probabilities.entries.where((e) => e.key != label).toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return entries;
  }

  /// Second place, but only when it is close enough that showing the winner on its own would
  /// make the answer look more settled than it is. Chalky against whole is why this is here,
  /// those two get mixed up in about one grain photo in ten.
  MapEntry<String, double>? get closeRunnerUp {
    if (confidence == null || others.isEmpty) return null;
    final runnerUp = others.first;
    return (confidence! - runnerUp.value) <= 0.15 ? runnerUp : null;
  }
}

enum SubjectKind { grain, leaf, unclear }

class Analysis {
  const Analysis({
    required this.subject,
    required this.grain,
    required this.leaf,
    required this.report,
  });

  final SubjectKind subject;
  final ModelResult grain;
  final ModelResult leaf;
  final String report;

  factory Analysis.fromJson(Map<String, dynamic> json) {
    final kind = (json['subject']?['kind'] as String?) ?? 'unclear';
    return Analysis(
      // a kind we do not know falls back to unclear, which shows both results. a new value
      // from the server must never make the app hide the answer the user wanted.
      subject: SubjectKind.values.firstWhere(
        (k) => k.name == kind,
        orElse: () => SubjectKind.unclear,
      ),
      grain: ModelResult.fromJson(
          (json['grain'] as Map).cast<String, dynamic>(), 'grade'),
      leaf: ModelResult.fromJson(
          (json['leaf'] as Map).cast<String, dynamic>(), 'disease'),
      report: (json['report'] as String?) ?? '',
    );
  }
}

/// Class names arrive as snake_case and the server does not touch them, so the app is never
/// parsing prose.
String prettyLabel(String raw) => raw
    .split('_')
    .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
    .join(' ');

/// healthy never gets shown as healthy. That class scored 0.000 on every source the model had
/// not trained on, so the most we can say is that nothing it knows about is there.
String prettyDisease(String raw) =>
    raw == 'healthy' ? 'No recognised disease' : prettyLabel(raw);
