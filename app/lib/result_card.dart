import 'package:flutter/material.dart';

import 'models.dart';

/// One model's answer. Shown normally when it applies to the photo, greyed out and collapsed
/// when it does not.
///
/// The greyed out one still shows its number if you tap it, because a technical person will
/// ask. It must never look as important as the one that applies. An answer that does not apply
/// is noise that happens to look like a result.
class ResultCard extends StatefulWidget {
  const ResultCard({
    super.key,
    required this.title,
    required this.result,
    required this.isDisease,
    required this.otherSubject,
  });

  final String title;
  final ModelResult result;

  /// Diseases go through the healthy rule, grades do not.
  final bool isDisease;

  /// What the photo looks like instead, so the greyed out card can say why.
  final String otherSubject;

  @override
  State<ResultCard> createState() => _ResultCardState();
}

class _ResultCardState extends State<ResultCard> {
  bool _expanded = false;

  String _display(String raw) =>
      widget.isDisease ? prettyDisease(raw) : prettyLabel(raw);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final r = widget.result;

    if (!r.applicable) {
      return Card(
        elevation: 0,
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.remove_circle_outline,
                      size: 18, color: theme.disabledColor),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '${widget.title}: not applicable',
                      style: theme.textTheme.titleSmall
                          ?.copyWith(color: theme.disabledColor),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'This photo looks like ${widget.otherSubject}, so the '
                '${widget.title.toLowerCase()} model has nothing meaningful to say about it.',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.disabledColor),
              ),
              if (r.assessed && r.label != null) ...[
                const SizedBox(height: 4),
                TextButton(
                  onPressed: () => setState(() => _expanded = !_expanded),
                  style: TextButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize: const Size(0, 32),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: Text(_expanded
                      ? 'Hide what it said anyway'
                      : 'Show what it said anyway'),
                ),
                if (_expanded)
                  Text(
                    '${_display(r.label!)}, '
                    '${((r.confidence ?? 0) * 100).round()}% confident. '
                    'Ignore this number.',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.disabledColor),
                  ),
              ],
            ],
          ),
        ),
      );
    }

    final runnerUp = r.closeRunnerUp;

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.title.toUpperCase(),
                style: theme.textTheme.labelSmall?.copyWith(
                  letterSpacing: 1.2,
                  color: theme.colorScheme.primary,
                )),
            const SizedBox(height: 6),
            Text(
              r.label == null ? 'No answer' : _display(r.label!),
              style: theme.textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),

            // show the number, do not bury it. a grade with no confidence next to it gets
            // more trust than the model has earned.
            Row(
              children: [
                Text('${((r.confidence ?? 0) * 100).round()}% confident',
                    style: theme.textTheme.bodyMedium),
                if (r.lowConfidence) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.tertiaryContainer,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text('uncertain',
                        style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.onTertiaryContainer)),
                  ),
                ],
              ],
            ),

            // only when the top two are close. showing it every time would make a confident
            // answer look like a coin flip.
            if (runnerUp != null) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.balance, size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Close call - could also be '
                        '${_display(runnerUp.key)} '
                        '(${(runnerUp.value * 100).round()}%)',
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // always shown when it is there, never depending on confidence
            if (r.caveat != null && r.caveat!.isNotEmpty) ...[
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline,
                      size: 16, color: theme.colorScheme.outline),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      r.caveat!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.outline),
                    ),
                  ),
                ],
              ),
            ],

            const SizedBox(height: 4),
            TextButton(
              onPressed: () => setState(() => _expanded = !_expanded),
              style: TextButton.styleFrom(
                padding: EdgeInsets.zero,
                minimumSize: const Size(0, 32),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text(_expanded ? 'Hide all scores' : 'Show all scores'),
            ),
            if (_expanded)
              ...r.probabilities.entries
                  .toList()
                  .let((list) => list
                    ..sort((a, b) => b.value.compareTo(a.value)))
                  .map((e) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Row(
                          children: [
                            SizedBox(
                              width: 150,
                              child: Text(_display(e.key),
                                  style: theme.textTheme.bodySmall),
                            ),
                            Expanded(
                              child: LinearProgressIndicator(
                                value: e.value,
                                minHeight: 6,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text('${(e.value * 100).round()}%',
                                style: theme.textTheme.bodySmall),
                          ],
                        ),
                      )),
          ],
        ),
      ),
    );
  }
}

extension<T> on T {
  R let<R>(R Function(T) op) => op(this);
}
