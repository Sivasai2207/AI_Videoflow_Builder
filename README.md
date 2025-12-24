# 🎬 AI VideoFlow Builder

> **Local-first AI video generation platform** — Transform text concepts into fully rendered social media videos using open-source AI models.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Compatible-purple.svg)](https://github.com/comfyanonymous/ComfyUI)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Phase Documentation](#phase-documentation)
- [Configuration](#configuration)
- [Development](#development)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

AI VideoFlow Builder is a comprehensive video generation pipeline that takes a simple text description and produces a complete social media video optimized for platforms like Instagram Reels, YouTube Shorts, and TikTok.

### The Pipeline

```
📝 Concept → 🎬 Storyboard → 🖼️ Keyframes → 🎥 Video → 🔊 Audio → 📤 Export
     ↓            ↓              ↓           ↓          ↓          ↓
   User        LLM-based      ComfyUI    FFmpeg     TTS/Music   Platform
   Input       Director       Images     Motion     Mixing      Presets
```

### Key Principles

- **Local-First**: All AI processing runs on your machine (Ollama, ComfyUI)
- **Reproducible**: Deterministic seeds ensure consistent regeneration
- **Modular**: Each phase can be run independently
- **Versioned**: Plan versions with full history tracking
- **Export-Ready**: One-click export for major social platforms

---

## ✨ Features

### Phase 1 — Infrastructure
- ✅ FastAPI backend with JWT authentication
- ✅ SQLModel database (SQLite/PostgreSQL)
- ✅ Redis + RQ job queue
- ✅ Next.js 16 frontend with dark theme
- ✅ Real-time progress via SSE

### Phase 2 — Director LLM
- ✅ Ollama integration for local LLM
- ✅ Comprehensive Director JSON schema
- ✅ 4-step creation wizard (Concept → Format → Style → Constraints)
- ✅ Interactive storyboard editor
- ✅ Plan versioning and approval workflow

### Phase 3 — Image Generation
- ✅ ComfyUI integration for Stable Diffusion
- ✅ Hero frames (style master + character anchor)
- ✅ Per-shot keyframe generation
- ✅ Idempotency caching (prevents duplicate renders)
- ✅ Approve/lock individual shots

### Phase 4 — Video + Audio + Export
- ✅ FFmpeg video generation from keyframes
- ✅ Ken Burns motion effects (zoom/pan)
- ✅ Clip stitching into final timeline
- ✅ TTS voiceover generation
- ✅ Background music integration
- ✅ Platform-specific export presets

### Phase 5 — Quality + Robustness
- ✅ QC module (blur detection, aspect ratio, face detection)
- ✅ Generate 3 variants per shot, pick best
- ✅ Video transitions (fade, dip-to-black)
- ✅ hero_plus_prev reference strategy for consistency
- ✅ Resumable pipeline (restart from last node)
- ✅ Health checks (ComfyUI, Ollama, FFmpeg, Redis)
- ✅ Export settings + SRT subtitle export

### Phase 6 — Productization + Scale
- ✅ Model Manager (install/verify/locate AI models)
- ✅ Performance benchmarking + safe defaults
- ✅ System diagnostics dashboard
- ✅ Renderer adapter (local ComfyUI, remote GPU ready)
- ✅ Setup wizard with guided configuration
- ✅ One-command launcher (`./run_local.sh`)
- ✅ Storage cleanup policies

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │Dashboard │ │Storyboard│ │  Audio   │ │  Export  │           │
│  │          │ │  Editor  │ │  Panel   │ │  Panel   │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP/SSE
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │  Auth   │ │Projects │ │  Plans  │ │ Images  │ │  Video  │  │
│  │ Router  │ │ Router  │ │ Router  │ │ Router  │ │ Router  │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      Services                            │   │
│  │  Ollama │ ComfyUI │ FFmpeg │ Storage │ Queue            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │ Redis Queue
┌─────────────────────────────────────────────────────────────────┐
│                      Worker (RQ)                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │   Director   │ │    Image     │ │    Video     │            │
│  │   Generate   │ │  Generation  │ │  Generation  │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
    │ Ollama  │          │ ComfyUI │          │ FFmpeg  │
    │  LLM    │          │  SD/XL  │          │ Encoder │
    └─────────┘          └─────────┘          └─────────┘
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Frontend** | Next.js 16, React 19 | User interface |
| **Backend** | FastAPI, SQLModel | REST API + ORM |
| **Queue** | Redis, RQ | Background jobs |
| **Database** | SQLite (dev), PostgreSQL (prod) | Data persistence |
| **LLM** | Ollama (llama3.2) | Plan generation |
| **Image Gen** | ComfyUI, SDXL | Keyframe rendering |
| **Video** | FFmpeg | Motion + encoding |
| **Audio** | gTTS, FFmpeg | Voiceover + mixing |

---

## 🚀 Quick Start

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **OS** | macOS 12+ / Ubuntu 20.04+ | macOS 13+ (Apple Silicon) |
| **RAM** | 16 GB | 32 GB |
| **Storage** | 50 GB free | 100 GB free |
| **Python** | 3.10+ | 3.11+ |
| **Node.js** | 18+ | 20+ |

### Required Dependencies

```bash
# macOS (using Homebrew)
brew install python@3.11 node redis ffmpeg

# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv nodejs npm redis-server ffmpeg
```

### Optional AI Services

| Service | Purpose | Installation |
|---------|---------|--------------|
| **Ollama** | Local LLM for plan generation | [ollama.ai](https://ollama.ai) |
| **ComfyUI** | Image generation (SDXL) | [github.com/comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) |

```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2

# ComfyUI - see their GitHub for full setup
```

### Installation

```bash
# Clone the repository
git clone https://github.com/Sivasai2207/AI_Videoflow_Builder.git
cd AI_Videoflow_Builder

# Install backend dependencies
cd apps/api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install frontend dependencies
cd ../web
npm install

# Return to root and create environment file
cd ../..
cp .env.example .env
```

### Configuration

Edit `.env` with your settings:

```env
# Required
SECRET_KEY=your-secret-key-here-min-32-chars

# Services (defaults work for local development)
REDIS_URL=redis://localhost:6379
OLLAMA_URL=http://localhost:11434
COMFYUI_URL=http://127.0.0.1:8188

# Optional
OLLAMA_MODEL=llama3.2
DATABASE_URL=sqlite:///./data/db/app.db
```

### Running the App

**Option 1: One-Command Launcher (Recommended)**

```bash
./run_local.sh
```

**Option 2: Manual Start**

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start API
cd apps/api && source venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 3: Start Worker (for background jobs)
cd apps/worker && source ../api/venv/bin/activate && rq worker

# Terminal 4: Start Frontend
cd apps/web && npm run dev
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **Web UI** | http://localhost:3000 | Main application |
| **API Docs** | http://localhost:8000/docs | Swagger documentation |
| **Health Check** | http://localhost:8000/health | API status |

### 🔐 Authentication

The app uses **self-registration**. There are no preset credentials.

1. Open http://localhost:3000
2. Click **"Sign Up"** to create an account
3. Enter your email and password
4. You're ready to create videos!

> **Note**: For local development, any email format works. Passwords must be at least 8 characters.

---

## 📁 Project Structure

```
AI_Videoflow_Builder/
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── main.py            # App entrypoint
│   │   ├── config.py          # Settings
│   │   ├── database.py        # DB setup
│   │   ├── dependencies.py    # FastAPI deps
│   │   ├── models/            # SQLModel tables
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── run.py
│   │   │   ├── shot.py
│   │   │   ├── asset.py
│   │   │   ├── video_clip.py
│   │   │   ├── audio_track.py
│   │   │   └── final_export.py
│   │   ├── routers/           # API endpoints
│   │   │   ├── auth.py
│   │   │   ├── projects.py
│   │   │   ├── runs.py
│   │   │   ├── shots.py
│   │   │   ├── plans.py
│   │   │   ├── images.py
│   │   │   ├── video.py
│   │   │   ├── audio.py
│   │   │   └── export.py
│   │   ├── services/          # Business logic
│   │   │   ├── __init__.py    # Auth service
│   │   │   ├── storage.py
│   │   │   ├── queue.py
│   │   │   ├── ollama.py
│   │   │   ├── comfyui.py
│   │   │   ├── director.py
│   │   │   ├── images.py
│   │   │   ├── video.py
│   │   │   └── audio.py
│   │   └── schemas/           # Pydantic schemas
│   │       └── director.py
│   │
│   ├── worker/                 # RQ background worker
│   │   ├── main.py
│   │   └── tasks/
│   │       ├── simulate_pipeline.py
│   │       ├── director_generate.py
│   │       ├── image_generation.py
│   │       └── video_generation.py
│   │
│   └── web/                    # Next.js frontend
│       ├── src/
│       │   ├── app/           # App router pages
│       │   │   ├── (dashboard)/
│       │   │   │   ├── dashboard/
│       │   │   │   ├── projects/[id]/
│       │   │   │   ├── monitor/
│       │   │   │   └── settings/
│       │   │   ├── login/
│       │   │   └── layout.tsx
│       │   ├── components/
│       │   │   ├── layout/
│       │   │   ├── projects/
│       │   │   ├── storyboard/
│       │   │   └── monitor/
│       │   └── lib/
│       │       ├── api.ts
│       │       ├── auth.tsx
│       │       └── sse.ts
│       └── package.json
│
├── workflows/                  # ComfyUI templates
│   └── templates/
│       ├── hero_style_master.json
│       ├── hero_character_anchor.json
│       └── keyframe_base.json
│
├── data/                       # Runtime data
│   ├── db/                    # SQLite database
│   ├── projects/              # Project files
│   └── exports/               # Final exports
│
├── .env.example
├── .gitignore
├── README.md
└── start.sh
```

---

## 📡 API Reference

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Create account |
| `/auth/login` | POST | Get JWT token |
| `/auth/me` | GET | Current user |

### Projects

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/projects` | GET | List projects |
| `/projects` | POST | Create project |
| `/projects/{id}` | GET | Get project |
| `/projects/{id}` | PATCH | Update project |
| `/projects/{id}` | DELETE | Delete project |

### Plans (Phase 2)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs/{id}/plan/generate` | POST | Generate plan via LLM |
| `/runs/{id}/plan` | GET | Get current plan |
| `/runs/{id}/plan` | PATCH | Update plan |
| `/runs/{id}/plan/approve` | POST | Approve and lock |
| `/runs/{id}/plan/versions` | GET | List versions |

### Images (Phase 3)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs/{id}/images/hero/start` | POST | Generate hero frames |
| `/runs/{id}/images/keyframes/start` | POST | Generate all keyframes |
| `/runs/{id}/shots/{sid}/keyframe/start` | POST | Generate single |
| `/runs/{id}/shots/{sid}/keyframe/approve` | POST | Approve keyframe |

### Video (Phase 4)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs/{id}/video/all/start` | POST | Generate all videos |
| `/runs/{id}/video/stitch` | POST | Stitch clips |
| `/runs/{id}/video/status` | GET | Generation status |

### Audio (Phase 4)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs/{id}/audio/voiceover/generate` | POST | Generate voiceover |
| `/runs/{id}/audio/music/set` | POST | Set music track |

### Export (Phase 4)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs/{id}/export/start` | POST | Start export |
| `/runs/{id}/export/status` | GET | Export status |
| `/runs/{id}/export/{eid}/download` | GET | Download file |

---

## 📚 Phase Documentation

### Phase 1 — Infrastructure Foundation

**Commit**: `feat: Phase 1 - Infrastructure foundation`

Establishes the core architecture:
- FastAPI backend with JWT authentication
- SQLModel database with User, Project, Run, Shot, Asset models
- Redis + RQ for background job processing
- Next.js frontend with dark creator theme
- Real-time SSE for progress updates

### Phase 2 — Director LLM Integration

**Commit**: `feat: Phase 2 - Director LLM + Storyboard Editor`

Adds AI-powered planning:
- Ollama integration for local LLM inference
- Director JSON schema with comprehensive validation
- 4-step creation wizard (Concept, Format, Style, Constraints)
- Interactive storyboard editor with 3-column layout
- Plan versioning with history restore

### Phase 3 — Image Generation via ComfyUI

**Commit**: `feat: Phase 3 - ComfyUI Image Generation`

Enables keyframe rendering:
- ComfyUI HTTP client for workflow submission
- Hero frames (style master + character anchor)
- Per-shot keyframe generation with consistency
- Idempotency caching prevents duplicate renders
- Approve/unlock controls per shot

### Phase 4 — Video + Audio + Export

**Commit**: `feat: Phase 4 - Video Generation + Audio + Export`

Completes the pipeline:
- FFmpeg video generation from keyframes
- Ken Burns motion effects (zoom, pan)
- Clip stitching into timeline
- TTS voiceover generation
- Music integration and mixing
- Platform export presets (Instagram, YouTube, TikTok)

### Phase 5 — Quality + Robustness

**Commit**: `feat: Phase 5 - QC, Variants, Transitions, Resumable Pipeline`

Makes the system creator-grade:
- QC module (blur detection, aspect ratio, face detection)
- Generate 3 variants per shot, pick winner
- Video transitions (fade, dip-to-black)
- hero_plus_prev reference strategy for character consistency
- Resumable pipeline (restarts from last incomplete node)
- Health checks for all external services
- Export settings + SRT subtitle export

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | JWT signing key |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `llama3.2` | LLM model name |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI server |
| `COMFYUI_OUTPUT_DIR` | `/data/comfyui/outputs` | ComfyUI outputs |

### Export Presets

| Preset | Resolution | Aspect | Bitrate |
|--------|------------|--------|---------|
| Instagram Reels | 1080×1920 | 9:16 | 8 Mbps |
| YouTube Shorts | 1080×1920 | 9:16 | 10 Mbps |
| TikTok | 1080×1920 | 9:16 | 8 Mbps |
| YouTube | 1920×1080 | 16:9 | 12 Mbps |

---

## 🔧 Development

### Running Tests

```bash
# Backend tests
cd apps/api
pytest

# Frontend tests
cd apps/web
npm test
```

### Code Style

```bash
# Backend
ruff check apps/api
black apps/api

# Frontend
cd apps/web
npm run lint
```

### Database Migrations

```bash
# Reset database (dev only)
rm data/db/app.sqlite
# Database is auto-created on API startup
```

---

## 🗺️ Roadmap

- [x] **Phase 1**: Infrastructure
- [x] **Phase 2**: Director LLM
- [x] **Phase 3**: Image Generation
- [x] **Phase 4**: Video + Audio + Export
- [x] **Phase 5**: Quality + Robustness
  - [x] QC module (blur, aspect ratio, face detection)
  - [x] Multiple variants per shot
  - [x] Video transitions (fade, dip-to-black)
  - [x] Health checks (ComfyUI, Ollama, FFmpeg, Redis)
  - [x] hero_plus_prev reference strategy
- [ ] **Phase 6**: Productization + Scale
  - [ ] Model manager UI
  - [ ] Performance profiling
  - [ ] Cloud deployment guide

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/amazing-feature`
3. Commit changes: `git commit -m 'feat: Add amazing feature'`
4. Push to branch: `git push origin feat/amazing-feature`
5. Open a Pull Request

### Commit Convention

```
feat: Add new feature
fix: Bug fix
docs: Documentation update
refactor: Code refactoring
test: Add tests
chore: Maintenance
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai) — Local LLM inference
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — Stable Diffusion workflows
- [FFmpeg](https://ffmpeg.org) — Video processing
- [FastAPI](https://fastapi.tiangolo.com) — Modern Python web framework
- [Next.js](https://nextjs.org) — React framework

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/Sivasai2207">Sivasai2207</a>
</p>
