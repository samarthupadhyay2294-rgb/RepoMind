"""Test external service connections."""

import asyncio
from app.services.qdrant_service import QdrantService
from app.embeddings.groq import get_embedding_provider


async def test_qdrant():
    """Test Qdrant connection."""
    try:
        service = QdrantService.from_settings()
        await service.ensure_collection(768)
        print("SUCCESS: Qdrant connection successful")
        return True
    except Exception as e:
        print(f"FAILED: Qdrant connection failed: {e}")
        return False


async def test_groq():
    """Test Groq connection."""
    try:
        provider = get_embedding_provider()
        test_vector = await provider.embed_query("test")
        print(f"SUCCESS: Groq connection successful (vector size: {len(test_vector)})")
        return True
    except Exception as e:
        print(f"FAILED: Groq connection failed: {e}")
        return False


async def main():
    print("Testing external service connections...")
    print()
    
    qdrant_ok = await test_qdrant()
    groq_ok = await test_groq()
    
    print()
    if qdrant_ok and groq_ok:
        print("SUCCESS: All connections successful - system ready!")
    else:
        print("FAILED: Some connections failed - check configuration")


if __name__ == "__main__":
    asyncio.run(main())