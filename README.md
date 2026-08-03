

# itosbot

A high-performance Telegram bot built with **aiogram 3** that converts photos, videos, and GIFs into custom emoji sticker packs. It features automatic tiling, intelligent background removal, dimension scaling, and seamless integration with a local Telegram Bot API server for improved reliability and rate-limit resilience.

## Features
- 🖼️ **Image Conversion**: Convert PNG, JPEG, and WEBP images into static custom emoji packs.
- 🎬 **Video/GIF Conversion**: Convert MP4, WEBM, and GIF files into animated custom emoji packs (≤5 seconds).
- 🎨 **Background Removal**: Remove solid backgrounds with adjustable color similarity and edge blending.
- 📐 **Custom Dimensions**: Specify tile grid size or let the bot auto-scale to Telegram's 50-tile limit.
- 🛡️ **Rate Limit Handling**: Built-in anti-flood middleware and graceful fallbacks for API restrictions.
- 🐳 **Dockerized**: Easy deployment with integrated `nginx` and local `telegram-bot-api` services.

## Installation

### Prerequisites
- Docker & Docker Compose
- Python 3.13+ (if running natively)
- A Telegram Bot Token
- Telegram API credentials (`TELEGRAM_API_ID` & `TELEGRAM_API_HASH`) *[Optional but recommended for the local API server]*

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/aiexz/itosbot.git
   cd itosbot
   ```
2. Create a `.env` file in the root directory and add your credentials:
   ```env
   BOT_TOKEN=your_bot_token_here
   TELEGRAM_API_ID=your_api_id_here
   TELEGRAM_API_HASH=your_api_hash_here
   ```
3. Build and run the services:
   ```bash
   # Production
   docker compose up --build -d

   # Development (with live code syncing & auto-restart)
   docker compose -f docker-compose.dev.yml up --build -d
   ```
The bot will start polling and automatically attempt to route requests through the local `telegram-bot-api` instance. If the local server is unreachable, it gracefully falls back to the default remote API.

## Usage

### Basic Interaction
- `/start` - Displays welcome message and links to usage examples.
- Simply send a photo, video, or GIF directly to the bot to convert it into a sticker pack.

### Advanced Conversion (`/convert`)
Append parameters to the `/convert` command to customize the output. Send the command along with the media file or as a caption:
```
/convert w=2 h=2 b=white b_sim=30 b_blend=10 name=MyCustomPack
```

**Parameters:**
| Flag | Description | Example |
|------|-------------|---------|
| `w` | Tile width multiplier (×100px) | `w=3` → 300px wide |
| `h` | Tile height multiplier (×100px) | `h=2` → 200px tall |
| `b` | Background color to remove (hex or name) | `b=ff0000` or `b=white` |
| `b_sim` | Color similarity threshold (0-100) | `b_sim=20` |
| `b_blend` | Edge smoothing/blend amount (0-100) | `b_blend=5` |
| `name` | Custom sticker pack title (max 50 chars) | `name=MyPack` |

### Platform Limits & Constraints
- 📁 Max file size: `20 MB`
- ⏱️ Max video/GIF duration: `5 seconds`
- 🧩 Max tiles per pack: `50` (100×100px each)
- 🖼️ Supported formats: PNG, JPEG, WEBP (images); MP4, WEBM, GIF (videos)
- ❌ HEIC/HEIF images are explicitly rejected
- 🐳 Video tiles are encoded with `libvpx-vp9` and automatically optimized to stay under Telegram's 64KB per tile limit.

## Project Structure
```
itosbot/
├── docker-compose.yml          # Production orchestration
├── docker-compose.dev.yml      # Development with Docker `watch`
├── pyproject.toml              # Python dependencies & metadata
└── src/
    ├── __main__.py             # Bot entry point & local API session setup
    ├── handlers/               # Message routing, commands & error handling
    ├── converter/              # Image/video processing, tiling & background removal
    ├── middlewares/            # Anti-flood & rate limiting logic
    └── settings.py             # Pydantic-based environment configuration
```

## Author
Developed by **Alex** (`@aiexz`). Contributions, feedback, and issue reports are welcome!
