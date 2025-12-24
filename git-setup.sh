#!/bin/bash
# =============================================================================
# AI VideoFlow Builder - Git Repository Setup
# =============================================================================
# This script initializes the git repository and creates the initial commit
# with all Phase 1-4 features included.
# =============================================================================

set -e

echo "🎬 AI VideoFlow Builder - Git Setup"
echo "===================================="

# Initialize repository
if [ ! -d ".git" ]; then
    echo "📦 Initializing Git repository..."
    git init
else
    echo "✓ Git repository already initialized"
fi

# Configure git (optional - uncomment to set)
# git config user.name "Sivasai2207"
# git config user.email "your-email@example.com"

# Stage all files
echo "📁 Staging files..."
git add -A

# Create initial commit with all phases
echo "📝 Creating initial commit..."
git commit -m "feat: AI VideoFlow Builder v0.4.0 - Complete Pipeline

🎬 AI VideoFlow Builder - Local-first AI video generation platform

Transform text concepts into fully rendered social media videos using
open-source AI models running entirely on your local machine.

## Features

### Phase 1: Infrastructure
- FastAPI backend with JWT authentication
- SQLModel database (SQLite/PostgreSQL)
- Redis + RQ job queue for background processing
- Next.js 16 frontend with dark creator theme
- Real-time SSE progress updates

### Phase 2: Director LLM
- Ollama integration for local LLM inference
- Comprehensive Director JSON schema with validation
- 4-step creation wizard (Concept → Format → Style → Constraints)
- Interactive storyboard editor with 3-column layout
- Plan versioning with full history tracking

### Phase 3: ComfyUI Image Generation
- ComfyUI client for Stable Diffusion XL workflows
- Hero frames (style master + character anchor)
- Per-shot keyframe generation with consistency
- Idempotency caching prevents duplicate renders
- Approve/lock individual shots

### Phase 4: Video + Audio + Export
- FFmpeg video generation from keyframes
- Ken Burns motion effects (zoom, pan)
- Clip stitching into final timeline
- TTS voiceover generation (gTTS)
- Background music integration
- Platform-specific export presets:
  - Instagram Reels (1080×1920)
  - YouTube Shorts (1080×1920)
  - TikTok (1080×1920)
  - YouTube (1920×1080)

## Tech Stack
- Backend: FastAPI, SQLModel, Redis, RQ
- Frontend: Next.js 16, React 19, TypeScript
- LLM: Ollama (llama3.2)
- Image: ComfyUI, SDXL
- Video: FFmpeg
- Audio: gTTS, FFmpeg

## Quick Start
\`\`\`bash
./start.sh
\`\`\`

Full documentation in README.md"

# Rename branch to dev
echo "🌿 Setting up branches..."
git branch -M dev

# Add remote (if not exists)
if ! git remote | grep -q "origin"; then
    echo "🔗 Adding remote origin..."
    git remote add origin git@github.com:Sivasai2207/AI_Videoflow_Builder.git
else
    echo "✓ Remote origin already configured"
fi

# Push to dev
echo "🚀 Pushing to dev branch..."
git push -u origin dev

echo ""
echo "✅ Repository setup complete!"
echo ""
echo "Next steps:"
echo "  1. Create main branch: git checkout -b main && git push -u origin main"
echo "  2. Set up branch protection rules on GitHub"
echo "  3. Create GitHub releases for each version"
echo ""
echo "Repository: https://github.com/Sivasai2207/AI_Videoflow_Builder"
