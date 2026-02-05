import os
import openai
import logging
import json
import argparse
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings

# --- Configuration ---
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL_NAME", "deepseek-r1:14b")
OLLAMA_EMBEDDING_MODEL_NAME = os.getenv(
    "OLLAMA_EMBEDDING_MODEL_NAME", "nomic-embed-text:v1.5"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("chromadb").setLevel(logging.WARNING)


# --- NEW: Custom Embedding Function for ChromaDB ---
class OllamaEmbeddingFunction(EmbeddingFunction):
    """
    Custom embedding function to connect ChromaDB with a local Ollama model.
    """

    def __init__(self, model_name: str, client: openai.OpenAI):
        self._model_name = model_name
        self._client = client

    def __call__(self, input: Documents) -> Embeddings:
        try:
            response = self._client.embeddings.create(
                model=self._model_name, input=input
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logging.error(f"Failed to get embeddings from Ollama: {e}")
            # Return a list of empty lists with the correct length to avoid crashing the caller
            return [[] for _ in input]


class RAG_CLI:
    def __init__(self, documents_path: str):
        if not os.path.exists(documents_path):
            raise FileNotFoundError(
                f"The specified documents file was not found: {documents_path}"
            )

        self.documents_path = documents_path
        self.client = openai.OpenAI(base_url=LOCAL_LLM_BASE_URL, api_key="not-needed")

        # --- MODIFIED: Initialize our custom embedding function ---
        self.embedding_function = OllamaEmbeddingFunction(
            OLLAMA_EMBEDDING_MODEL_NAME, self.client
        )

        self.db_client = chromadb.Client()  # In-memory client
        self.collection = None

        self._load_and_embed_documents()

    def _load_and_embed_documents(self):
        docs = []
        with open(self.documents_path, "r", encoding="utf-8") as f:
            for line in f:
                docs.append(json.loads(line))

        if not docs:
            raise ValueError(
                "No documents found in the provided file. Cannot start RAG CLI."
            )

        project_name = (
            docs[0].get("metadata", {}).get("project_name", "default_project")
        )
        collection_name = f"rag_{project_name.lower().replace(' ', '_')}"

        logging.info(f"Initializing ChromaDB collection: '{collection_name}'")

        # --- MODIFIED: Pass the embedding function to ChromaDB ---
        self.collection = self.db_client.get_or_create_collection(
            name=collection_name, embedding_function=self.embedding_function
        )

        # Check if documents are already loaded to avoid re-embedding
        # Get existing IDs to only add new documents
        existing_ids = set(self.collection.get(include=[])["ids"])

        docs_to_add = []
        for doc in docs:
            doc_id = doc["metadata"]["source"]
            if doc_id not in existing_ids:
                docs_to_add.append(doc)

        if not docs_to_add:
            logging.info(
                f"Collection is already up-to-date with {self.collection.count()} documents."
            )
            return

        logging.info(
            f"Adding {len(docs_to_add)} new documents to the knowledge base..."
        )

        # --- MODIFIED & SIMPLIFIED: Let ChromaDB handle embedding via our function ---
        contents = [doc["content"] for doc in docs_to_add]
        metadatas = [doc["metadata"] for doc in docs_to_add]
        ids = [doc["metadata"]["source"] for doc in docs_to_add]

        # Chroma will call our OllamaEmbeddingFunction automatically
        if contents:
            self.collection.add(documents=contents, metadatas=metadatas, ids=ids)

        logging.info(
            f"Successfully loaded. Collection now has {self.collection.count()} documents."
        )

    def query(self, user_question: str, n_results: int = 5):
        # --- This method now works correctly with no changes ---
        retrieved_results = self.collection.query(
            query_texts=[user_question],
            n_results=n_results,
        )

        retrieved_docs = retrieved_results["documents"][0]
        retrieved_metadatas = retrieved_results["metadatas"][0]

        if not retrieved_docs:
            return "I could not find any relevant information in the knowledge base to answer your question."

        context_str = ""
        for i, doc in enumerate(retrieved_docs):
            source = retrieved_metadatas[i].get("source", "N/A")
            context_str += f"--- Context from: {source} ---\n{doc}\n\n"

        system_prompt = (
            "You are an expert AI assistant for a software project. "
            "Your task is to answer the user's question based *only* on the provided context. "
            "Be concise and clear in your answer. If the context does not contain the answer, "
            "state that you cannot answer based on the information you have. "
            "Cite your sources by mentioning the file or directory path from the context."
        )

        user_prompt = f"--- CONTEXT ---\n{context_str}--- END CONTEXT ---\n\nUser Question: {user_question}"

        try:
            response = self.client.chat.completions.create(
                model=LOCAL_LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error during LLM call: {e}")
            return "Sorry, I encountered an error while trying to generate an answer."

    def start_chat_loop(self):
        """Starts the interactive command-line chat loop."""
        print("\n--- Project RAG Chat ---")
        print(
            f"Knowledge base: '{self.collection.name}' with {self.collection.count()} documents."
        )
        print("Ask questions about your project. Type 'exit' or 'quit' to end.")

        while True:
            try:
                question = input("\n> ")
                if question.lower() in ["exit", "quit"]:
                    print("Exiting chat. Goodbye!")
                    break

                answer = self.query(question)
                print(f"\nAssistant: {answer}")

            except KeyboardInterrupt:
                print("\nExiting chat. Goodbye!")
                break
            except Exception as e:
                logging.error(f"An error occurred in the chat loop: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="A RAG CLI to chat with your project's knowledge base."
    )
    parser.add_argument(
        "documents_file",
        help="Path to the 'rag_documents.jsonl' file generated by the analyzer.",
    )
    args = parser.parse_args()

    try:
        rag_cli = RAG_CLI(args.documents_file)
        rag_cli.start_chat_loop()
    except (FileNotFoundError, ValueError) as e:
        logging.error(f"Initialization failed: {e}")
    except Exception as e:
        logging.error(f"A critical error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()
