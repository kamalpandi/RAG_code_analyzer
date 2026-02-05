import os
import re
import faiss
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from sentence_transformers import SentenceTransformer
from typing import List, Dict

# --- Configuration ---
CONFIG = {
    "knowledge_base_file": "knowledge_base.txt",
    "embedding_model": "all-MiniLM-L6-v2",  # Fast, local model
    "llm_model": "gpt-4o-mini",
    "child_chunk_size": 384,  # Optimal for embedding model context window
    "top_k_retrieval": 5,
}

# --- Setup ---
load_dotenv()
console = Console()

# Securely load the OpenAI API key
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        raise TypeError
except TypeError:
    console.print(
        "[bold red]Error: OPENAI_API_KEY environment variable not set.[/bold red]"
    )
    exit()

console.print("[bold yellow]RAG Pipeline Initializing...[/bold yellow]")


class RAGPipeline:
    """A robust RAG pipeline using a parent-child chunking strategy."""

    def __init__(self, config: Dict):
        self.config = config
        self.embedding_model = SentenceTransformer(config["embedding_model"])
        self.parent_chunks: List[str] = []
        self.child_chunks: List[str] = []
        self.child_to_parent_map: List[int] = []
        self.vector_store: faiss.Index = None
        console.print(
            f"[green]Using embedding model: {config['embedding_model']}[/green]"
        )
        console.print(f"[green]Using LLM model: {config['llm_model']}[/green]")
        console.print(f"[green]Child chunk size: {config['child_chunk_size']}[/green]")

    def _create_parent_child_chunks(self, text: str) -> None:
        """
        Splits text into larger parent chunks and smaller child chunks.
        Maps child chunks to their parent's index for efficient lookup.
        """
        # Split the document into parent chunks by paragraphs
        self.parent_chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
        console.print(
            f"[bold cyan]Total raw paragraphs (potential parent chunks): {len(self.parent_chunks)}[/bold cyan]"
        )

        child_chunk_size = self.config["child_chunk_size"]

        for i, p_chunk in enumerate(self.parent_chunks):
            if len(p_chunk) <= child_chunk_size:
                self.child_chunks.append(p_chunk)
                self.child_to_parent_map.append(i)
            else:
                # Split larger parent chunks into smaller child chunks by sentences
                sentences = re.split(r"(?<=[.!?])\s+", p_chunk)
                current_child = ""
                for sentence in sentences:
                    if len(current_child) + len(sentence) + 1 <= child_chunk_size:
                        current_child += sentence + " "
                    else:
                        self.child_chunks.append(current_child.strip())
                        self.child_to_parent_map.append(i)
                        current_child = sentence + " "
                if current_child:
                    self.child_chunks.append(current_child.strip())
                    self.child_to_parent_map.append(i)

    def build_vector_store(self, text: str) -> None:
        """Loads text, creates chunks, and builds the FAISS vector store."""
        console.print("\n[cyan]Step 1: Chunking document...[/cyan]")
        self._create_parent_child_chunks(text)
        console.print(
            f"Created [bold magenta]{len(self.parent_chunks)}[/bold magenta] parent chunks and [bold magenta]{len(self.child_chunks)}[/bold magenta] child chunks."
        )
        if len(self.child_chunks) == 0:
            console.print(
                "[bold red]ERROR: No chunks were created. Check knowledge base content.[/bold red]"
            )
            return

        console.print(
            f"[cyan]Step 2: Generating embeddings with '{self.config['embedding_model']}' for {len(self.child_chunks)} child chunks...[/cyan]"
        )
        embeddings = self.embedding_model.encode(
            self.child_chunks, convert_to_tensor=False, show_progress_bar=True
        )
        console.print("[green]Embedding generation complete.[/green]")

        d = embeddings.shape[1]
        self.vector_store = faiss.IndexFlatL2(d)
        self.vector_store.add(np.array(embeddings))
        console.print(
            f"[green]FAISS index created with {self.vector_store.ntotal} vectors of dimension {d}.[/green]"
        )

    def retrieve_context(self, query: str) -> List[str]:
        """Retrieves relevant parent chunks for a given query."""
        console.print("\n" + "=" * 50)
        console.print("[bold yellow]1. RETRIEVAL STEP[/bold yellow]")
        console.print(f"[yellow]User Query:[/yellow] {query}")

        query_vector = self.embedding_model.encode([query])

        console.print(
            f"[cyan]Searching FAISS index for top {self.config['top_k_retrieval']} child chunks...[/cyan]"
        )
        _, indices = self.vector_store.search(
            np.array(query_vector), k=self.config["top_k_retrieval"]
        )

        # Get the parent chunk indices using the map
        retrieved_child_indices = indices[0]
        console.print(
            f"[green]Retrieved child chunk indices (in FAISS): {retrieved_child_indices}[/green]"
        )

        parent_indices = {self.child_to_parent_map[i] for i in retrieved_child_indices}
        console.print(
            f"[green]Mapped to unique parent chunk indices: {sorted(list(parent_indices))}[/green]"
        )

        # Retrieve the unique parent chunks
        retrieved_context = [
            self.parent_chunks[i] for i in sorted(list(parent_indices))
        ]

        console.print(
            f"[bold green]Retrieved {len(retrieved_context)} unique context chunks (Parent Chunks).[/bold green]"
        )

        # Log the retrieved context (truncated)
        for i, chunk in enumerate(retrieved_context):
            truncated_chunk = chunk[:80] + "..." if len(chunk) > 80 else chunk
            console.print(f"  [dim]Context {i + 1}: '{truncated_chunk}'[/dim]")
        console.print("=" * 50 + "\n")

        return retrieved_context

    def generate_response(self, query: str, context: List[str]) -> str:
        """Generates a response from the LLM based on the query and context."""
        console.print("=" * 50)
        console.print("[bold yellow]2. GENERATION STEP[/bold yellow]")

        if not context:
            console.print("[red]No context retrieved. Skipping LLM call.[/red]")
            return "I could not find any relevant information in the knowledge base to answer your question."

        context_str = "\n---\n".join(context)
        prompt = f"""
        You are an expert technical assistant. Your task is to provide a detailed and comprehensive answer to the user's question based *only* on the context provided below.

        Follow these rules strictly:
        1. Synthesize the information from all provided context chunks.
        2. Structure your response clearly. Use headings or bullet points for readability.
        3. If the context does not contain the answer, state that you cannot answer based on the provided information.

        CONTEXT:
        {context_str}

        USER'S QUESTION:
        {query}
        """

        # Log the prompt size
        console.print(f"[cyan]Final prompt length: {len(prompt)} characters.[/cyan]")
        # Log the beginning of the context for sanity check
        console.print(f"[dim]Context starts with: '{context_str[:100]}...'[/dim]")

        console.print(
            f"Asking '{self.config['llm_model']}' to generate a response...", end=""
        )
        try:
            response = client.chat.completions.create(
                model=self.config["llm_model"],
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert technical assistant for developers.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            console.print(" [green]Done![/green]")
            return response.choices[0].message.content
        except Exception as e:
            console.print(
                f" [bold red]Failed![/bold red]\nAn error occurred with the OpenAI API: {e}"
            )
            return "Sorry, I encountered an error while generating a response."


if __name__ == "__main__":
    console.print(
        f"[cyan]Attempting to load knowledge base file: {CONFIG['knowledge_base_file']}[/cyan]"
    )
    try:
        with open(CONFIG["knowledge_base_file"], "r", encoding="utf-8") as f:
            knowledge_base_text = f.read()
            console.print(
                f"[green]Successfully loaded {len(knowledge_base_text)} characters from file.[/green]"
            )
    except FileNotFoundError:
        console.print(
            f"[bold red]Error: Knowledge base file not found at '{CONFIG['knowledge_base_file']}'.[/bold red]"
        )
        exit()

    pipeline = RAGPipeline(CONFIG)
    pipeline.build_vector_store(knowledge_base_text)

    console.print("\n" + "#" * 60)
    console.print("[bold blue]Chatbot is ready! Type 'exit' to quit.[/bold blue]")
    console.print("#" * 60 + "\n")

    while True:
        try:
            user_query = console.input("[bold]You:[/bold] ")
            if user_query.lower() == "exit":
                break

            console.print("\n" + "=" * 60)
            console.print(
                f"[bold white on blue] Processing Query: {user_query} [/bold white on blue]"
            )
            console.print("=" * 60)

            # 1. Retrieve context
            retrieved_chunks = pipeline.retrieve_context(user_query)

            # 2. Generate final answer
            final_response = pipeline.generate_response(user_query, retrieved_chunks)

            console.print("\n[bold blue]Chatbot Final Response:[/bold blue]")
            console.print(Markdown(final_response))
            console.print("=" * 60 + "\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(
                f"[bold red]An unexpected error occurred in the chat loop: {e}[/bold red]"
            )
            import traceback

            traceback.print_exc()

    console.print("\n[bold]Goodbye! 👋[/bold]")
