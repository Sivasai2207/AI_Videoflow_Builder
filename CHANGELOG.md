# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2024-12-24

### Added - Phase 4: Video + Audio + Export
- **Video Generation**
  - `VideoClip` model for tracking preview/final/stitched clips
  - FFmpeg-based video generation from keyframes
  - Ken Burns motion effects (zoom_in, zoom_out, pan)
  - Clip stitching with concat demuxer
  - Video router with `/video/shots/{id}/start`, `/video/all/start`, `/video/stitch`
  
- **Audio Integration**
  - `AudioTrack` model for voiceover and music
  - TTS voiceover generation (gTTS with fallback)
  - Auto-script builder from Director JSON
  - Music library system
  - Audio mixing and muxing
  - Audio router with voiceover/music endpoints
  
- **Export Pipeline**
  - `FinalExport` model for export jobs
  - Platform-specific presets (Instagram, YouTube, TikTok)
  - Resolution/codec optimization
  - Export router with download endpoint
  
- **Frontend**
  - `AudioPanel` component (voiceover script + music selector)
  - `ExportPanel` component (platform presets + download)
  - `videoApi`, `audioApi`, `exportApi` in API client

## [0.3.0] - 2024-12-24

### Added - Phase 3: ComfyUI Image Generation
- **ComfyUI Integration**
  - `ComfyUIClient` for HTTP workflow submission
  - `poll_until_complete()` for job tracking
  - `collect_outputs()` for file collection
  - Mock fallback when ComfyUI unavailable
  
- **Image Generation**
  - `ImageGenerationJob` model with idempotency caching
  - Hero frames: style master + character anchor
  - Per-shot keyframe generation
  - Workflow templates (JSON with placeholders)
  
- **Database Updates**
  - Shot model extended with `keyframe_status`, `keyframe_asset_id`
  - Asset model with `HERO_FRAME_STYLE`, `HERO_FRAME_CHARACTER`, `KEYFRAME` roles
  
- **Worker Tasks**
  - `generate_hero_frames()`
  - `generate_keyframe()` / `generate_keyframes_all()`
  - `regenerate_keyframe()` with seed options
  
- **Frontend**
  - Image generation controls in StoryboardEditor
  - Per-shot Generate/Regenerate/Approve/Unlock buttons
  - Hero assets preview

## [0.2.0] - 2024-12-24

### Added - Phase 2: Director LLM + Storyboard Editor
- **Director JSON Schema**
  - Comprehensive Pydantic schema (v1.0)
  - Auto-validation (duration sum, timestamps, seeds)
  - Auto-fixing logic
  
- **Ollama Integration**
  - `OllamaClient` for local LLM
  - Dynamic prompt building
  - JSON repair with retry
  - Mock fallback when Ollama unavailable
  
- **Database Updates**
  - `DirectorPlanVersion` model for versioning
  - Run status: `PLANNING` → `PLANNED` → `APPROVED`
  - `active_plan_version_id`, `plan_locked` fields
  
- **Plans Router**
  - `POST /plan/generate` - LLM generation
  - `PATCH /plan` - Update with versioning
  - `POST /plan/approve` - Lock plan
  - `GET /plan/versions` - History
  
- **Frontend**
  - 4-step CreateReelWizard (Concept → Format → Style → Constraints)
  - 3-column StoryboardEditor (Timeline | Detail | Bible)
  - Version history modal

## [0.1.0] - 2024-12-24

### Added - Phase 1: Infrastructure Foundation
- **Backend (FastAPI)**
  - JWT authentication with bcrypt
  - SQLModel ORM with SQLite
  - Models: User, Project, Run, Shot, Asset, RenderJob
  - Routers: auth, projects, runs, shots, assets
  - Redis + RQ job queue
  - SSE for real-time progress
  
- **Frontend (Next.js 16)**
  - Dark creator theme with glassmorphism
  - Protected routes with auth context
  - Dashboard with project grid
  - Project detail with tabs
  - CreateProjectWizard component
  
- **Infrastructure**
  - `start.sh` for running all services
  - Environment configuration
  - Storage service for file paths

---

## Git Workflow

### Branch Strategy
- `main` - Production releases
- `dev` - Development branch
- `feat/*` - Feature branches

### Merge Commits

#### Phase 1 → dev
```
Merge: feat/phase-1-infrastructure → dev

Phase 1: Infrastructure Foundation

- FastAPI backend with JWT authentication
- SQLModel database (User, Project, Run, Shot, Asset)
- Redis + RQ job queue for background processing
- Next.js 16 frontend with dark theme
- Real-time SSE progress updates
- Storage service and file structure
```

#### Phase 2 → dev
```
Merge: feat/phase-2-director-llm → dev

Phase 2: Director LLM + Storyboard Editor

- Ollama integration for local LLM inference
- Director JSON schema with validation
- 4-step creation wizard
- Interactive storyboard editor
- Plan versioning with history
```

#### Phase 3 → dev
```
Merge: feat/phase-3-comfyui-images → dev

Phase 3: ComfyUI Image Generation

- ComfyUI client for Stable Diffusion
- Hero frames and keyframe generation
- Idempotency caching
- Approve/lock per shot
- Workflow templates
```

#### Phase 4 → dev
```
Merge: feat/phase-4-video-audio-export → dev

Phase 4: Video + Audio + Export

- FFmpeg video generation from keyframes
- Ken Burns motion effects
- TTS voiceover and music
- Platform export presets
- Download functionality
```

#### dev → main (Release)
```
Merge: dev → main

Release v0.4.0: Full Video Generation Pipeline

Complete local-first AI video generation platform:
- Text concept → Director JSON (LLM)
- Storyboard → Keyframes (ComfyUI)
- Keyframes → Video (FFmpeg)
- Audio integration (TTS + Music)
- Platform export (Instagram, YouTube, TikTok)
```
