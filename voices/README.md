# Piper voices

Put Piper voice files in this folder.

Each Piper voice needs two files:

```text
<voice>.onnx
<voice>.onnx.json
```

The app supports both layouts.

Flat layout:

```text
voices/
  en_US-joe-medium.onnx
  en_US-joe-medium.onnx.json
  it_IT-riccardo-x_low.onnx
  it_IT-riccardo-x_low.onnx.json
```

Official nested Piper layout:

```text
voices/
  en/en_US/joe/medium/en_US-joe-medium.onnx
  en/en_US/joe/medium/en_US-joe-medium.onnx.json
  it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx
  it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx.json
```

The root project file `piper_voices.json` is used as the catalogue. The `.env`
file does not need one variable per language anymore. If a voice is not installed,
the text translation still works and the UI shows a friendly warning.
