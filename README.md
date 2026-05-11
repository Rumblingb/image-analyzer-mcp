# Image Analyzer MCP Server

An MCP (Model Context Protocol) server that provides image analysis tools using **Pillow (PIL)** — no external APIs required. All processing is done locally.

## Features

- **analyze_image** — Get dimensions, format, color mode, file size, aspect ratio, and DPI from an image file
- **analyze_image_base64** — Same analysis from a base64-encoded image string
- **get_dominant_colors** — Extract dominant colors as hex values with RGB components and approximate coverage percentages
- **get_image_metadata** — Read EXIF data including GPS coordinates, camera make/model, date taken, orientation, and more
- **convert_image** — Convert between PNG, JPEG, WEBP, and GIF formats, returned as base64

## Requirements

- Python 3.10+
- `mcp>=1.0.0`
- `Pillow>=10.0.0`

## Installation

```bash
cd image-analyzer-mcp
pip install -r requirements.txt
```

## Usage

### Run with stdio transport (default — for MCP clients)

```bash
python server.py
```

This starts the server over stdio, suitable for integration with MCP clients (e.g., Claude Desktop, Cursor, etc.).

### Run with SSE transport (HTTP)

```bash
python server.py --transport sse --host 0.0.0.0 --port 8080
```

Requires `uvicorn` (`pip install uvicorn`).

## MCP Client Configuration

Add to your MCP client config:

```json
{
  "mcpServers": {
    "image-analyzer": {
      "command": "python",
      "args": ["/path/to/image-analyzer-mcp/server.py"],
      "transport": "stdio"
    }
  }
}
```

## Tool Reference

### `analyze_image`

Analyze an image file.

| Parameter    | Type   | Required | Description          |
|-------------|--------|----------|----------------------|
| `image_path` | string | yes      | Path to image file   |

**Returns:** dimensions, format, mode, file size, aspect ratio, DPI.

### `analyze_image_base64`

Analyze an image from base64-encoded data.

| Parameter     | Type   | Required | Description               |
|--------------|--------|----------|--------------------------|
| `base64_data` | string | yes      | Base64-encoded image data |

**Returns:** Same as `analyze_image`, but without the file path.

### `get_dominant_colors`

Extract dominant colors from an image.

| Parameter    | Type   | Required | Default | Description                        |
|-------------|--------|----------|---------|------------------------------------|
| `image_path` | string | yes      | —       | Path to image file                 |
| `count`      | integer| no       | 5       | Number of dominant colors (max 128)|

**Returns:** List of dominant colors with hex values, RGB components, and approximate percentage coverage.

### `get_image_metadata`

Extract EXIF metadata from an image.

| Parameter    | Type   | Required | Description          |
|-------------|--------|----------|----------------------|
| `image_path` | string | yes      | Path to image file   |

**Returns:** EXIF data including GPS coordinates, camera info, date taken, orientation, etc.

### `convert_image`

Convert an image to a different format.

| Parameter       | Type   | Required | Default | Description                          |
|----------------|--------|----------|---------|--------------------------------------|
| `image_path`    | string | yes      | —       | Path to image file                   |
| `target_format` | string | yes      | —       | PNG, JPEG, WEBP, or GIF              |
| `quality`       | integer| no       | 85      | Output quality (1-100, JPEG/WEBP only)|

**Returns:** Base64-encoded converted image data.

## License

MIT

## Pricing

$19/mo — https://buy.stripe.com/dRm6oJ4Hd2Jugek0wz1oI0m
