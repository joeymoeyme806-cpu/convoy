# Convoy

Pack your entire Python project into a single `.convoy` file.

## Install

```bash
pip install -e .
```

## Usage

**1. Create a `convoy.toml` in your project root:**

```toml
[[file]]
main = "main.py"

[[settings]]
compression = 6
libs = "pyside6, PIL"
```

Or run `convoy-settings` to build one visually.

**2. Build:**

```bash
convoy build          # animated output
convoy build --fast   # silent, just ships it
```

**3. Run:**

```bash
convoy run myapp.convoy
```

**4. Settings GUI:**

```bash
convoy-settings
```

## How it works

1. All `.py` files are compiled to `.pyc` (optimised bytecode)
2. Requested libraries are copied from your Python environment
3. Everything is compressed into a single `.convoy` file
4. On run: extracted to a private temp directory, executed, then wiped — nothing stays on disk

## .convoy format

```
[8 bytes]  magic header (CONVOY\x00\x01)
[4 bytes]  compressed payload length
[N bytes]  zlib-compressed bundle
```
