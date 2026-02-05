# Project RAG Chat CLI

This script provides an interactive command-line interface (CLI) to "chat" with your project's knowledge base. It is the second part of a two-stage process, designed to work with the output of the `hierarchical_summarization.py` script.

Using a Retrieval-Augmented Generation (RAG) pipeline, this tool allows you to ask natural language questions about your codebase and receive detailed, source-cited answers from a local Large Language Model (LLM).

## Overview

After the `hierarchical_summarization.py` script has analyzed a project and produced a `rag_documents.jsonl` file, this CLI takes over. It loads the generated summaries into an in-memory vector database (ChromaDB), allowing for powerful semantic search. When you ask a question, the tool retrieves the most relevant summaries and feeds them to an LLM to generate a comprehensive answer.

## How It Works

The script follows a standard RAG pipeline, optimized for local execution with tools like Ollama.

1. **Initialization & Loading:**

      - The script starts by loading the `rag_documents.jsonl` file.
      - It creates a unique collection name for the project within an in-memory ChromaDB instance (e.g., `rag_my-project`).

2. **Embedding with Local Models:**

      - A key feature is the `OllamaEmbeddingFunction` class. This custom function acts as a bridge between ChromaDB and a local embedding model served via an OpenAI-compatible API (like Ollama).
      - When documents are added to the collection, ChromaDB automatically calls this function to convert the text summaries into vector embeddings using the specified local model (e.g., `nomic-embed-text`).
      - The process is idempotent: it checks for existing documents in the collection and only adds and embeds new ones, making subsequent runs on an updated `jsonl` file fast and efficient.

3. **The RAG Query Process:**

      - **Question:** You ask a question in the CLI (e.g., "How does user authentication work?").
      - **Retrieval:** The script embeds your question using the same local model. ChromaDB then performs a similarity search to find the most relevant document summaries from its vector store.
      - **Augmentation:** The retrieved summaries (the "context") are formatted and combined with your original question into a detailed prompt.
      - **Generation:** This combined prompt is sent to a local chat-completion LLM (e.g., `deepseek-r1:14b`). The LLM is instructed to answer the user's question based *only* on the provided context and to cite its sources (the file/directory paths from the summaries).

4. **Interactive Chat:**

      - The final, synthesized answer is printed to the console.
      - The script then loops, ready for your next question, maintaining the knowledge base in memory.

## Key Features

- **Interactive Chat Interface:** A simple and intuitive CLI for asking questions about your code.
- **Local-First RAG Pipeline:** Fully functional with locally-run models via Ollama or other OpenAI-compatible servers, ensuring privacy and cost-effectiveness.
- **Custom Embedding Function for ChromaDB:** Seamlessly integrates local embedding models with ChromaDB's powerful vector search capabilities.
- **In-Memory Vector Database:** Uses ChromaDB for fast, in-memory semantic search without requiring external database setup.
- **Source-Cited Answers:** The LLM is prompted to include the source file or directory for each piece of information it uses, allowing you to easily verify answers.
- **Idempotent Loading:** Efficiently updates the knowledge base by only processing documents that haven't been seen before.

## Usage

**Prerequisite:** You must first run `hierarchical_summarization.py` to generate a `rag_documents.jsonl` file for your project.

1. **Start the CLI by pointing it to your documents file:**

    ```bash
    python rag_cli.py path/to/your/findings/my-project_YYYYMMDD_HHMMSS/rag_documents.jsonl
    ```

2. **Wait for the documents to be loaded and embedded:**

    ```log
    INFO:root:Initializing ChromaDB collection: 'rag_my-project'
    INFO:root:Adding 152 new documents to the knowledge base...
    INFO:root:Successfully loaded. Collection now has 152 documents.
    ```

3. **Ask questions at the prompt:**

    ```bash
    --- Project RAG Chat ---
    Knowledge base: 'rag_my-project' with 152 documents.
    Ask questions about your project. Type 'exit' or 'quit' to end.

    > What is the purpose of the main.py file?

    Assistant: Based on the provided context, the `main.py` file serves as the primary entry point for the application. It is responsible for initializing the core components, setting up the application server, and starting the event loop. (Source: main.py)

    > How are database connections managed?

    Assistant: According to the `db/database.py` summary, database connections are managed by a connection pool that is initialized once when the application starts. Functions within this file provide a way to get a connection from the pool and release it when the operation is complete. (Source: db/database.py)

    > exit
    Exiting chat. Goodbye!
    ```

## Configuration (via Environment Variables)

This script uses the same environment variables as the summarizer, plus one for the embedding model.

- **`LOCAL_LLM_BASE_URL`**: The base URL of your LLM API endpoint.
  - Default: `http://localhost:11434/v1`
- **`LOCAL_LLM_MODEL_NAME`**: The name of the model to use for **generating answers**.
  - Default: `deepseek-r1:14b`
- **`OLLAMA_EMBEDDING_MODEL_NAME`**: The name of the model to use for **creating embeddings**. Must be an embedding model available on your local server.
  - Default: `nomic-embed-text:v1.5`
