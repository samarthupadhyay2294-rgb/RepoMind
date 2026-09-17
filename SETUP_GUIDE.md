# RepoMind Setup Guide

## Prerequisites

1. **Python 3.11+** and **Node.js 18+** installed
2. **Git** installed and accessible from command line
3. **Qdrant Vector Database** running locally
4. **Ollama running locally** with `gemma4:31b-cloud` available (chat; no API key needed)
5. **Mistral API key** for embeddings (`mistral-embed`)

## Step 1: Install Qdrant (Vector Database)

### Option A: Docker (Recommended)
```bash
docker run -p 6333:6333 -p 6334:6334 -d qdrant/qdrant
```

### Option B: Qdrant Cloud
1. Sign up at [https://cloud.qdrant.io/](https://cloud.qdrant.io/)
2. Create a new cluster
3. Get your API URL and key
4. Update `.env` with your cloud credentials

### Option C: Local Installation
Download from [https://github.com/qdrant/qdrant/releases](https://github.com/qdrant/qdrant/releases)

## Step 2: Start local Ollama (chat model)

RepoMind uses your locally running Ollama instance as its LLM provider.
You manage Ollama separately — RepoMind never runs `ollama pull`,
`ollama serve`, or `ollama run`.

1. Start Ollama separately (it must already be running before RepoMind starts).
2. Ensure `gemma4:31b-cloud` is available in your local Ollama.
3. RepoMind connects to `http://localhost:11434`. No API key is required —
   leave `OLLAMA_API_KEY` empty in `backend/.env`:
```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=
OLLAMA_MODEL=gemma4:31b-cloud
```

## Step 3: Configure Environment Variables

Update `backend/.env` with your actual values:

```dotenv
# Local Ollama (primary chat provider; no key required)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=
OLLAMA_MODEL=gemma4:31b-cloud

# Mistral embeddings (unchanged: mistral-embed, 1024 dimensions)
MISTRAL_API_KEY=your_actual_mistral_api_key_here
MISTRAL_EMBEDDING_MODEL=mistral-embed
EMBEDDING_DIMENSION=1024

# Qdrant Configuration
QDRANT_URL=http://localhost:6333  # or your Qdrant Cloud URL
QDRANT_API_KEY=                    # leave empty for local, add for cloud
QDRANT_COLLECTION_NAME=repomind

# Database (SQLite for development)
DATABASE_URL=sqlite+aiosqlite:///./repomind.db
```

## Step 4: Initialize Database

```bash
cd backend
.venv\Scripts\python.exe -m scripts.init_db
```

## Step 5: Start Services

### Backend
```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm run dev
```

## Step 6: Test the Complete Workflow

1. Open http://localhost:3000 in your browser
2. Click "Add Repository"
3. Enter a Git URL (e.g., `https://github.com/facebook/react`)
4. Give it a name and click "Add Repository"
5. Wait for indexing to complete (status changes to "indexed")
6. Click on the repository to open chat
7. Ask a question about the codebase

## Troubleshooting

### Qdrant Connection Issues
- Verify Qdrant is running: `curl http://localhost:6333/`
- Check if port 6333 is available
- Try restarting Qdrant

### Ollama Connection Issues
- Verify Ollama is already running separately: it must be reachable at `http://localhost:11434`
- If you see "Ollama is not reachable at http://localhost:11434", start Ollama first, then retry RepoMind
- If you see "Ollama model gemma4:31b-cloud is unavailable", ensure that model is available in your local Ollama
- Check your Mistral API key/quota if embedding/indexing fails (embeddings still use `mistral-embed`)

### Git Clone Issues
- Ensure Git is installed: `git --version`
- Check network connectivity
- Verify the repository URL is accessible

### Database Issues
- Delete `repomind.db` and re-run initialization
- Check file permissions
- Ensure SQLite drivers are installed

## Architecture Overview

The system follows this workflow:

```
USER
  ↓
Add Repository (Git URL validation)
  ↓
Create Repository Record (SQLite)
  ↓
Prepare Isolated Workspace (acquisition.py)
  ↓
Clone Repository (Git shallow clone)
  ↓
File Discovery + .gitignore Filtering (discovery.py)
  ↓
Secret/Binary/Size Filtering (filters.py)
  ↓
Parse Files (parsers.py)
  ↓
Chunk Code + Generate Metadata (chunking.py)
  ↓
Generate Embeddings (Mistral mistral-embed, 1024 dimensions)
  ↓
Store Chunks in Qdrant (qdrant_service.py)
  ↓
Repository Status = INDEXED
  ↓
USER ASKS QUESTION
  ↓
Retrieve Relevant Code from Qdrant (retrieval.py)
  ↓
LangGraph Agent (graph.py)
  ↓
Plan Investigation (plan_node)
  ↓
Use Read-Only Code Tools (tools/)
  ↓
Collect + Evaluate Evidence (evaluate_node)
  ↓
Enough Evidence? (Conditional routing)
  ├── NO → Retrieve / Tools → Evaluate again
  └── YES
        ↓
      Local Ollama (gemma4:31b-cloud → LLM via llm_models.py)
        ↓
Grounded Answer + File/Line Citations
        ↓
FastAPI (routes_chat.py)
        ↓
Next.js + shadcn/ui (Frontend)
        ↓
USER SEES ANSWER + SOURCES
```

## Security Notes

- All repository content is treated as untrusted data
- Git credentials are never stored or logged
- Workspace isolation prevents cross-repository access
- Tools are read-only and repository-scoped
- No arbitrary code execution
- API keys are never exposed in logs or responses