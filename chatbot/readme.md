# Advanced RAG Chatbot with Parent-Child Chunking

This project implements a sophisticated Retrieval-Augmented Generation (RAG) pipeline in Python. It leverages a powerful **Parent-Child Chunking** strategy to provide accurate, context-rich answers to user queries based on a local knowledge base.

The system uses a local sentence-transformer for efficient embeddings, FAISS for high-speed vector search, and OpenAI's GPT models for response generation.

## Key Features

- **Parent-Child Chunking**: Improves retrieval accuracy by searching over small, specific "child" chunks while providing the LLM with larger, more meaningful "parent" chunks for better contextual understanding.
- **Local Embeddings**: Utilizes the `sentence-transformers` library to generate high-quality text embeddings locally, ensuring speed and privacy.
- **High-Performance Vector Search**: Employs Facebook AI's FAISS library for fast and memory-efficient similarity searches.
- **Modular & Configurable**: The entire pipeline is encapsulated in a clean `RAGPipeline` class and is easily configurable through a central `CONFIG` dictionary.
- **Interactive CLI**: A user-friendly command-line interface powered by the `rich` library for a polished experience.

## How It Works: The Pipeline

The RAG pipeline operates in two main phases: an offline indexing phase and an online retrieval/generation phase.

### 1\. Indexing Phase (Building the Vector Store)

When the script is first run, it processes the document specified in `knowledge_base_file`.

#### a. Parent-Child Chunking

This is the core of the retrieval strategy.

1. **Parent Chunks**: The source text is first split into large, logical chunks based on paragraphs (`\n\n`). These serve as the rich context that will eventually be sent to the LLM.
2. **Child Chunks**: Each parent chunk is then broken down further into smaller, fixed-size child chunks. This is done by combining sentences until the `child_chunk_size` is reached.
3. **Mapping**: A crucial mapping is created that links every child chunk back to its original parent chunk index (`child_to_parent_map`).

<!-- end list -->

- **Why this strategy?** Small child chunks are better for embedding and similarity search because they contain focused, specific information. This leads to more accurate retrieval. However, LLMs perform better with more context. By retrieving the small child chunk but providing its larger parent chunk to the LLM, we get the best of both worlds.

#### b. Embedding and Indexing

1. The list of **child chunks** is fed into the `SentenceTransformer` model (`all-MiniLM-L6-v2` by default) to create a vector embedding for each one.
2. These vectors are then indexed in a FAISS `IndexFlatL2` vector store, which is optimized for fast similarity search using L2 (Euclidean) distance.

### 2\. Query Phase (Answering User Questions)

This phase is triggered every time the user enters a query.

#### a. Retrieval

1. The user's query is converted into a vector embedding using the same sentence-transformer model.
2. The FAISS vector store is searched to find the top `k` **child chunks** that are most semantically similar to the query vector.
3. The `child_to_parent_map` is used to identify the unique **parent chunks** corresponding to the retrieved child chunks.
4. These unique parent chunks become the context for the next step.

#### b. Generation

1. A detailed prompt is constructed, containing the user's original query and the retrieved parent chunks.
2. The prompt explicitly instructs the LLM (e.g., `gpt-4o-mini`) to answer the query based *only* on the provided context. This grounds the model and prevents it from hallucinating or using external knowledge.
3. The complete prompt is sent to the OpenAI API, which generates a final, synthesized answer.
4. The response is streamed back and displayed to the user in a formatted way.

## Configuration

The script's behavior can be easily modified through the `CONFIG` dictionary at the top of the file:

- `"knowledge_base_file"`: The path to the `.txt` file that contains your source text.
- `"embedding_model"`: The name of the `sentence-transformers` model to use for generating embeddings. `all-MiniLM-L6-v2` is a great choice for its balance of speed and performance.
- `"llm_model"`: The identifier for the OpenAI model you wish to use for generating the final answers (e.g., `"gpt-4o-mini"`, `"gpt-4o"`).
- `"child_chunk_size"`: The target maximum character length for the smaller child chunks. This value should be tuned based on the embedding model's context window and the nature of your source text.
- `"top_k_retrieval"`: The number of child chunks to retrieve from the vector store for a given query. A larger `k` provides more context but may also introduce more noise.

## Usage

To run the chatbot, execute the script from your terminal:

```bash
python your_script_name.py
```

The script will first build the vector store from the knowledge base. Once you see the message "Chatbot is ready\!", you can start asking questions.

- Type your question and press Enter.
- The chatbot will retrieve relevant context and generate a response.
- To end the session, type `exit` and press Enter.
