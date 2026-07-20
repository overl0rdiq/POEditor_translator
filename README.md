# POEditor AI Translate

A small Python script that fills in the missing translations in a POEditor CSV export using the Claude API. It produces context-aware Arabic instead of the flat, literal output you get from generic machine translation.

The script keeps the following intact:

- Placeholders such as `{current}` and `{total}`
- HTML tags such as `<strong>` and `<br/>`
- Literal `\n` newlines
- Brand and technical names (Tuta, Gmail, IMAP, and so on)

It also skips any string whose context field is marked `do not translate` or `deprecated`.

## Requirements

```bash
pip install -r requirements.txt
```

## API key

The key is never stored in the code. It is read from an environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

You can get a key at https://console.anthropic.com

## Usage

```bash
python ai_translate.py
```

This writes a new file, `Tuta_Client_Arabic_AI_Translated.csv`, in the same format as the input, ready to import back into POEditor.

## Configuration

All options are at the top of [`ai_translate.py`](ai_translate.py):

| Option | Description |
|--------|-------------|
| `INPUT_CSV` | Source POEditor export |
| `OUTPUT_CSV` | Name of the generated file |
| `MODEL` | Claude model to use |
| `BATCH_SIZE` | Strings per request (smaller is more accurate, larger is faster) |
| `OVERWRITE_EXISTING` | `True` to retranslate everything, including already-translated rows |
| `GLOSSARY` | Fixed terminology to keep translations consistent |

## CSV column layout

The script expects the standard POEditor export layout:

```
key , translation , (empty) , (empty) , context , source(EN)
```

The source column is the last one. Adjust `KEY_COL`, `TRANSLATION_COL`, and `CONTEXT_COL` if your file differs.

## Resuming

Progress is saved to `.translation_cache.json` after every batch. If the run is interrupted, start it again and it continues from where it stopped without retranslating what is already done.
