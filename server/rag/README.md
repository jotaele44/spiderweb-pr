# Retrieval-Augmented Generation (RAG) Layer

This directory contains scaffolding for the retrieval layer that will
augment PRIIS query responses with evidence-based context. The goal of
the retrieval layer is to search across multiple modalities (SQL,
vector, geospatial, and graph) to find relevant entities and
documents, and to assemble them into a unified set of candidate
results for the language model.

## Components

### `retrieval.py`

Defines placeholder functions:

- `keyword_search(query: str)` – perform a keyword or full-text
  search over text fields in the database.
- `vector_search(query: str)` – perform a vector similarity search
  using embeddings stored in a vector database (e.g., `pgvector`,
  `Qdrant`, `Pinecone`).
- `geo_search(latitude: float, longitude: float, radius_km: float)` –
  perform a geospatial search for entities near a point.
- `graph_search(node_id: str)` – explore relationships between
  entities in a graph database.
- `hybrid_retrieve(query: str)` – aggregate results from the
  different retrieval strategies. When implementing this function
  you should de-duplicate and rank results across modalities.

All functions currently return empty results and should be filled out
as your data infrastructure matures.

## Next Steps

1. Choose a vector store (e.g., `pgvector`, `Qdrant`, `Pinecone`) and
   implement `vector_search` with embeddings computed from your
   documents.
2. Implement `keyword_search` by leveraging full-text search
   capabilities in PostgreSQL or a search engine like Elasticsearch.
3. Use PostGIS to implement `geo_search` over the `sites` table.
4. Evaluate whether a graph database (e.g., Neo4j) is appropriate for
   `graph_search`, or if a relational representation suffices.
5. Combine the results in `hybrid_retrieve` and feed them into the
   LLM via your orchestrator.