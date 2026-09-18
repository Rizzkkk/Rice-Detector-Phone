import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'api.dart';
import 'result_screen.dart';

void main() => runApp(const RiceScannerApp());

class RiceScannerApp extends StatelessWidget {
  const RiceScannerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Rice Scanner',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3D7A3D)),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}

enum _Stage { idle, working }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _picker = ImagePicker();
  final _api = RiceApi();

  _Stage _stage = _Stage.idle;
  ApiFailure? _failure;
  File? _lastPhoto;

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _capture(ImageSource source) async {
    setState(() => _failure = null);

    XFile? shot;
    try {
      // image_picker shrinks the photo itself, which is faster and uses less memory than
      // doing it in dart. 1280 is what the server would shrink it to anyway, so this only
      // saves upload time and data. it does not change what the model sees.
      shot = await _picker.pickImage(
        source: source,
        maxWidth: 1280,
        maxHeight: 1280,
        imageQuality: 88,
      );
    } catch (e) {
      // this fires when camera permission is denied for good, among other things
      setState(() => _failure = const ApiFailure(
            FailureKind.rejected,
            'Could not open the camera. Check the app has camera permission in Settings.',
          ));
      return;
    }

    if (shot == null) return; // user backed out, that is not an error

    final photo = File(shot.path);
    setState(() {
      _stage = _Stage.working;
      _lastPhoto = photo;
    });

    try {
      final analysis = await _api.analyze(photo);
      if (!mounted) return;
      setState(() => _stage = _Stage.idle);
      await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ResultScreen(photo: photo, analysis: analysis),
      ));
    } on ApiFailure catch (f) {
      if (!mounted) return;
      setState(() {
        _stage = _Stage.idle;
        _failure = f;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _stage = _Stage.idle;
        _failure = const ApiFailure(
            FailureKind.server, 'Something went wrong. Try again.');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_stage == _Stage.working) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (_lastPhoto != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Image.file(_lastPhoto!,
                      height: 160, width: 160, fit: BoxFit.cover),
                ),
              const SizedBox(height: 28),
              const CircularProgressIndicator(),
              const SizedBox(height: 20),
              Text('Analysing', style: theme.textTheme.titleMedium),
              const SizedBox(height: 6),
              Text('Usually a few seconds',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.outline)),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Rice Scanner')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 12),
            Text('Photograph rice grain or a rice leaf',
                style: theme.textTheme.headlineSmall),
            const SizedBox(height: 12),
            Text(
              'Grain is graded as whole, broken, chalky or stained. Leaves are checked for '
              'four common diseases. The app works out which you photographed.',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.outline),
            ),
            const SizedBox(height: 8),
            Text(
              'Analysis runs on a server, so this needs an internet connection.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.outline),
            ),

            if (_failure != null) ...[
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: theme.colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.error_outline,
                        size: 18, color: theme.colorScheme.onErrorContainer),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(_failure!.message,
                          style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onErrorContainer)),
                    ),
                  ],
                ),
              ),
            ],

            const Spacer(),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                'For the best result: fill the frame with the subject, use a plain '
                'background, and avoid shadow across it.',
                style: theme.textTheme.bodySmall,
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: () => _capture(ImageSource.camera),
              icon: const Icon(Icons.camera_alt_outlined),
              label: const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('Take photo'),
              ),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: () => _capture(ImageSource.gallery),
              icon: const Icon(Icons.photo_library_outlined),
              label: const Text('Choose an existing photo'),
            ),
          ],
        ),
      ),
    );
  }
}
