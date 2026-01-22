import os
from typing import Any, Dict, List, Optional

# The Google Generative AI library
from google import genai
from google.genai import types

from src.config.common_settings import LOCATION, PROJECT_ID, credentials
from src.utils.logger import logger


class EmbeddingError(RuntimeError):
    """
    Raised when an embedding operation completes without producing valid embeddings.
    """

class EmbeddingsService:
    """
    A LangChain-compatible embedding class for Google's gemini-embedding-001 model.

    This class allows for embedding documents and queries using the state-of-the-art
    Google Generative AI models, supporting dynamic task types and output dimensionality.

    To use, you must have the `google-generativeai` package installed and a
    GOOGLE_API_KEY environment variable set.
    """
    def __init__(
        self,
        model: str = "gemini-embedding-001",
        dimensionality: Optional[int] = None,
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the EmbeddingsService.

        Args:
            model: The embedding model to use (default: "gemini-embedding-001").
            dimensionality: Optional output dimensionality for embeddings.
            api_key: Optional Google API key. If not provided, will use environment variable.
            **kwargs: Additional keyword arguments for future compatibility.
        """
        self.client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION, credentials=credentials)
        self.model = model
        self.dimensionality = dimensionality

    def _coerce_embedding_values(self, item: Any) -> List[float]:
        """
        Normalize different SDK return shapes into a plain list[float].
        Supports objects with 'values' attr, dicts with 'values'/'embedding', or raw lists.
        """
        try:
            if item is None:
                return []
            # Object with .values (Vertex/GenAI SDK embedding object)
            vals = getattr(item, "values", None)
            if vals is not None:
                return list(vals)
            # Dict-like
            if isinstance(item, dict):
                if "values" in item and isinstance(item["values"], list):
                    return list(item["values"])  # type: ignore[return-value]
                if "embedding" in item and isinstance(item["embedding"], list):
                    return list(item["embedding"])  # type: ignore[return-value]
            # Already a list of floats
            if isinstance(item, list):
                return item
        except Exception:
            pass
        return []

    def _coerce_embeddings_batch(self, response: Any) -> List[List[float]]:
        """Extract list[list[float]] from various embed_content response shapes."""
        try:
            # Prefer attribute access
            embs = getattr(response, "embeddings", None)
            if isinstance(embs, list) and embs:
                return [self._coerce_embedding_values(e) for e in embs]
            # Dict-like access
            if isinstance(response, dict):
                embs2 = response.get("embeddings")
                if isinstance(embs2, list):
                    return [self._coerce_embedding_values(e) for e in embs2]
        except Exception:
            pass
        return []

    def _coerce_embedding_single(self, response: Any) -> List[float]:
        """Extract single embedding as list[float] from response."""
        try:
            # Attribute: response.embedding or response.embeddings[0]
            one = getattr(response, "embedding", None)
            if one is not None:
                return self._coerce_embedding_values(one)
            embs = getattr(response, "embeddings", None)
            if isinstance(embs, list) and embs:
                return self._coerce_embedding_values(embs[0])
            # Dict-like
            if isinstance(response, dict):
                if "embedding" in response:
                    return self._coerce_embedding_values(response["embedding"])  # type: ignore[index]
                if "embeddings" in response and isinstance(response["embeddings"], list):
                    return self._coerce_embedding_values(response["embeddings"][0])  # type: ignore[index]
        except Exception:
            pass
        return []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents. This is the primary method used by LangChain
        for vectorization when adding documents to a vector store.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of embeddings, where each embedding is a list of floats.
        """
        if not texts or not isinstance(texts, list):
            raise ValueError("embed_documents expects a non-empty list of strings")
        if any((not isinstance(t, str)) or (t == "") for t in texts):
            raise ValueError("embed_documents received one or more invalid text entries")
        
        # The 'RETRIEVAL_DOCUMENT' task type is typically used for this method.
        try:
            response = self.client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.dimensionality,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
            embs = self._coerce_embeddings_batch(response)
            if not embs:
                raise EmbeddingError("embed_documents returned no embeddings")
            if len(embs) != len(texts):
                raise EmbeddingError(
                    f"embed_documents returned {len(embs)} embeddings for {len(texts)} inputs"
                )
            if any(len(e) == 0 for e in embs):
                raise EmbeddingError("embed_documents returned one or more empty embeddings")
            return embs
        except Exception as e:
            logger.error("EmbeddingsService: embed_documents failed: %s", e, exc_info=True)
            raise EmbeddingError("Failed to embed documents") from e

    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query. This method is used for embedding the user's
        search query before comparing it to the documents in the vector store.

        Args:
            text: The query string to embed.

        Returns:
            The embedding for the query as a list of floats.
        """
        if not text or not isinstance(text, str):
            raise ValueError("embed_query expects a non-empty string")
            
        # The 'RETRIEVAL_QUERY' task type is specifically for this purpose.
        try:
            response = self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.dimensionality,
                    task_type="RETRIEVAL_QUERY",
                ),
            )
            emb = self._coerce_embedding_single(response)
            if not emb:
                raise EmbeddingError("embed_query returned no embedding")
            return emb
        except Exception as e:
            logger.error("EmbeddingsService: embed_query failed: %s", e, exc_info=True)
            raise EmbeddingError("Failed to embed query") from e
        
    # --- User-Requested Custom Method ---

    def create_embeddings(
        self,
        texts: list[str],
        dimensionality: Optional[int] = None,
    ) -> List[List[float]]:
        """
        A flexible method to create embeddings for a list of texts, allowing
        for on-the-fly specification and dimensionality.

        This method directly maps to your requested function signature.

        Args:
            texts: A list of strings to embed.
            dimensionality: The desired output embedding dimension. If None,
                          the class's default is used.

        Returns:
            A list of embeddings, one for each input text.
        """
        if not texts or not isinstance(texts, list):
            raise ValueError("create_embeddings expects a non-empty list of strings")
        if any((not isinstance(t, str)) or (t == "") for t in texts):
            raise ValueError("create_embeddings received one or more invalid text entries")

        # Use the method's dimensionality if provided, otherwise fall back to the class default.
        output_dim = dimensionality if dimensionality is not None else self.dimensionality

        try:
            response = self.client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=output_dim),
            )
            embs = self._coerce_embeddings_batch(response)
            if not embs:
                raise EmbeddingError("create_embeddings returned no embeddings")
            if len(embs) != len(texts):
                raise EmbeddingError(
                    f"create_embeddings returned {len(embs)} embeddings for {len(texts)} inputs"
                )
            if any(len(e) == 0 for e in embs):
                raise EmbeddingError("create_embeddings returned one or more empty embeddings")
            return embs
        except Exception as e:
            logger.error("EmbeddingsService: create_embeddings failed: %s", e, exc_info=True)
            raise EmbeddingError("Failed to create embeddings") from e


# --- Minimal helpers for ad-hoc testing via `python -c` ---
def test_embed(text: str, model: Optional[str] = None, dimensionality: Optional[int] = None) -> List[float]:
    """
    Minimal helper: return a single embedding for quick testing.

    Example:
        python -c "from src.services.gemini_embeddings import test_embed; emb=test_embed('hello world'); print(len(emb), emb[:8])"
    """
    effective_model = model or os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-005")
    service = EmbeddingsService(model=effective_model, dimensionality=dimensionality)
    return service.embed_query(text)


def test_embed_many(texts: List[str], model: Optional[str] = None, dimensionality: Optional[int] = None) -> List[List[float]]:
    """
    Minimal helper: return embeddings for a list of texts.

    Example:
        python -c "from src.services.gemini_embeddings import test_embed_many; embs=test_embed_many(['a','b']); print([len(e) for e in embs])"
    """
    effective_model = model or os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-005")
    service = EmbeddingsService(model=effective_model, dimensionality=dimensionality)
    return service.embed_documents(texts)