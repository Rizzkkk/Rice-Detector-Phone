import 'dart:io';

import 'package:flutter/material.dart';

import 'models.dart';
import 'result_card.dart';

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.photo, required this.analysis});

  final File photo;
  final Analysis analysis;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final unclear = analysis.subject == SubjectKind.unclear;

    final grainCard = ResultCard(
      title: 'Grain',
      result: analysis.grain,
      isDisease: false,
      otherSubject: 'a leaf',
    );
    final leafCard = ResultCard(
      title: 'Leaf',
      result: analysis.leaf,
      isDisease: true,
      otherSubject: 'grain',
    );

    // the one that applies goes first. on unclear both apply and grain leads, same as the
    // report line.
    final cards = analysis.leaf.applicable && !analysis.grain.applicable
        ? [leafCard, grainCard]
        : [grainCard, leafCard];

    return Scaffold(
      appBar: AppBar(title: const Text('Result')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Image.file(photo,
                height: 200, width: double.infinity, fit: BoxFit.cover),
          ),
          const SizedBox(height: 16),

          if (analysis.report.isNotEmpty)
            Text(analysis.report,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.outline)),

          // this has to look like the app being careful, not like it broke
          if (unclear) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.tertiaryContainer,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.help_outline, size: 18),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'This photo did not clearly look like either grain or a rice leaf, so '
                      'both results are shown and neither is certain. For a better answer, '
                      'retake it against a plain background with the subject filling the frame.',
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ),
          ],

          const SizedBox(height: 16),
          cards[0],
          const SizedBox(height: 12),
          cards[1],
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.camera_alt_outlined),
            label: const Text('Scan another'),
          ),
        ],
      ),
    );
  }
}
