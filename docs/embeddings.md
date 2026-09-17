# Embeddings setup

Indexing and code search need a Mistral embedding key. Without it, indexing
stops immediately with a configuration error and no repository content is
processed.

## Setup

1. Copy `backend/.env.example` to `backend/.env` (never commit `.env`).
2. Set `MISTRAL_API_KEY` in `backend/.env`:

   ```dotenv
   MISTRAL_API_KEY=your_actual_mistral_api_key_here
   MISTRAL_EMBEDDING_MODEL=mistral-embed
   EMBEDDING_DIMENSION=1024
   ```

3. Restart the backend so it picks up the new value, then retry indexing.

`EMBEDDING_DIMENSION` must stay `1024` for `mistral-embed`. There is no
local embedding provider — the only supported backend is Mistral, and it is
only called during indexing and retrieval.
