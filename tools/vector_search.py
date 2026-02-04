"""
Vector search using FAISS index and OpenAI embeddings
Loads pre-generated FAISS index and uses OpenAI for query embeddings
"""

import json
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict
import os
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

class VectorSearch:
    """
    Vector search implementation using FAISS and OpenAI embeddings
    - Loads pre-generated FAISS index from disk
    - Uses OpenAI for user query embeddings
    - Returns top-k most similar products
    """

    # Similarity threshold for filtering results
    # Only return products with similarity score >= this threshold
    # Range: 0.0-1.0 (higher = more strict filtering)
    # NOTE: Lowered to 0.30 to fix empty results issue
    SIMILARITY_THRESHOLD = 0.30

    def __init__(
        self,
        index_path: str = "embeddings/vector_store/products.index",
        metadata_path: str = "embeddings/vector_store/metadata.json"
    ):
        """
        Initialize vector search
        
        Args:
            index_path: Path to FAISS index file
            metadata_path: Path to product metadata JSON file
        """
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        
        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=api_key)
        self.embedding_model = "text-embedding-3-small"
        
        # Load FAISS index and metadata
        self._load_index()
        self._load_metadata()
        
        logger.info(f"✅ VectorSearch initialized")
        logger.info(f"   Index: {self.index_path}")
        logger.info(f"   Products: {len(self.metadata)}")
        logger.info(f"   Vectors: {self.index.ntotal}")
    
    def _load_index(self):
        """Load FAISS index from disk"""
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"FAISS index not found: {self.index_path}\n"
                f"Run 'python create_embeddings.py' first to generate embeddings."
            )
        
        logger.info(f"📊 Loading FAISS index from: {self.index_path}")
        self.index = faiss.read_index(str(self.index_path))
        logger.info(f"✅ FAISS index loaded: {self.index.ntotal} vectors")
    
    def _load_metadata(self):
        """Load product metadata from disk"""
        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Metadata file not found: {self.metadata_path}\n"
                f"Run 'python create_embeddings.py' first to generate metadata."
            )
        
        logger.info(f"📦 Loading metadata from: {self.metadata_path}")
        with open(self.metadata_path, 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)
        logger.info(f"✅ Metadata loaded: {len(self.metadata)} products")
    
    def _get_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate embedding for user query using OpenAI
        
        Args:
            query: User's search query
            
        Returns:
            numpy array of embedding vector
        """
        logger.info(f"🤖 Generating query embedding via OpenAI...")
        
        response = self.client.embeddings.create(
            input=[query],
            model=self.embedding_model
        )
        
        embedding = np.array(response.data[0].embedding, dtype='float32')
        
        logger.info(f"✅ Query embedding generated (dim: {len(embedding)})")
        
        return embedding
    
    def search(self, query: str, top_k: int = 5, metadata_filter: dict = None) -> List[Dict]:
        """
        Search for products similar to query
        
        Args:
            query: Natural language search query
            top_k: Number of results to return
            
        Returns:
            List of top-k most similar products with scores
        """
        logger.info(f"🔍 Vector search: '{query}' (top_k={top_k})")
        
        # Generate query embedding using OpenAI
        query_embedding = self._get_query_embedding(query)
        
        # Reshape for FAISS (expects 2D array)
        query_vector = query_embedding.reshape(1, -1)
        
        # Search FAISS index
        # Returns: distances (L2), indices of nearest neighbors
        distances, indices = self.index.search(query_vector, top_k)
        
        # Format results with similarity threshold filtering
        results = []
        filtered_count = 0

        for distance, idx in zip(distances[0], indices[0]):
            if idx < len(self.metadata):  # Valid index
                product = self.metadata[idx].copy()

                # Apply metadata filter BEFORE similarity threshold
                if metadata_filter and not self._matches_filter(product, metadata_filter):
                    continue

                # Convert L2 distance to similarity score (lower distance = higher similarity)
                # Normalize to 0-1 range for easier interpretation
                similarity_score = 1 / (1 + distance)

                # Filter by similarity threshold
                if similarity_score >= self.SIMILARITY_THRESHOLD:
                    product['similarity_score'] = float(similarity_score)
                    product['distance'] = float(distance)
                    results.append(product)

                    logger.info(f"  ✓ [{len(results)}] {product['name']} (score: {similarity_score:.3f}, dist: {distance:.3f})")
                else:
                    filtered_count += 1
                    logger.debug(
                        f"  ✗ Filtered: {product['name']} "
                        f"(score: {similarity_score:.3f} < threshold: {self.SIMILARITY_THRESHOLD})"
                    )
            else:
                logger.warning(f"  ⚠️ Invalid index returned: {idx}")

        if filtered_count > 0:
            logger.info(f"ℹ️  Filtered {filtered_count}/{top_k} results below similarity threshold ({self.SIMILARITY_THRESHOLD})")

        logger.info(f"✅ Found {len(results)} relevant results")

        return results

    def _matches_filter(self, product: dict, filter_spec: dict) -> bool:
        """Generic filter matching - supports $eq, $ne, $in, $nin, $gt, $lt"""
        for field, condition in filter_spec.items():
            if isinstance(condition, dict):
                # Operator-based: {"category": {"$ne": "Cold-Pressed Oils"}}
                for op, value in condition.items():
                    if op == "$eq" and product.get(field) != value:
                        return False
                    elif op == "$ne" and product.get(field) == value:
                        return False
                    elif op == "$in" and product.get(field) not in value:
                        return False
                    elif op == "$nin" and product.get(field) in value:
                        return False
                    elif op == "$gt" and product.get(field) <= value:
                        return False
                    elif op == "$lt" and product.get(field) >= value:
                        return False
            else:
                # Direct match: {"category": "Superfoods"}
                if product.get(field) != condition:
                    return False
        return True


# Singleton instance
_vector_search_instance = None

def get_vector_search() -> VectorSearch:
    """
    Get or create VectorSearch singleton instance
    
    Returns:
        VectorSearch instance
    """
    global _vector_search_instance
    
    if _vector_search_instance is None:
        logger.info("🔄 Initializing VectorSearch (first call)...")
        _vector_search_instance = VectorSearch()
    
    return _vector_search_instance