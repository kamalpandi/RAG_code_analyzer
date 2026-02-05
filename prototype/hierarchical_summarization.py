import os
import openai
import logging
import json
import argparse
import hashlib
import tiktoken
import concurrent.futures
import threading

from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from openai import APIError, BadRequestError

# --- Configuration ---
# Load LLM settings from environment variables with defaults
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL_NAME", "deepseek-r1:7b")

# Maximum concurrent requests to the LLM API
MAX_WORKERS = os.getenv("MAX_WORKERS", 32)

# Token threshold to trigger chunked summarization for large directories
# Set to ~75% of an 16k context window to be safe. Adjust if your model's context is different.
CONTEXT_TOKEN_THRESHOLD = 8000

# List of directories and files to exclude from analysis
EXCLUSION_LIST = [
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".uv",
    "uv.lock",
    "node_modules",
    ".vscode",
    ".idea",
    ".DS_Store",
    "pb_data",
    "pb_public",
    "migrations",
    ".project_analyzer_cache",  # Exclude the cache dir itself
]

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class ProjectAnalyzer:
    def __init__(self, project_dir, force_reanalyze=False, max_workers=MAX_WORKERS):
        self.project_dir = Path(project_dir).resolve()
        self.script_dir = Path(__file__).parent.resolve()
        self.force_reanalyze = force_reanalyze
        self.max_workers = int(max_workers)
        self.cache_lock = threading.Lock()

        # --- Refactored Path Management ---
        # Cache directory is stable to persist cache between runs
        self.cache_dir = self.script_dir / ".project_analyzer_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_path = self.cache_dir / f"findings_{self.project_dir.name}.json"

        # Output directory is timestamped for storing reports from a specific run
        self.output_dir = (
            self.script_dir
            / "findings"
            / f"{self.project_dir.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load prompts from external JSON file
        self._load_prompts()

        # Initialize OpenAI client for local LLM
        self.client = openai.OpenAI(base_url=LOCAL_LLM_BASE_URL, api_key="not-needed")

        # --- Refactored State Management ---
        # Load existing cache into memory or initialize a new one
        self._load_or_init_cache()

        logging.info("Initialized ProjectAnalyzer:")
        logging.info(f"- Project: {self.project_dir}")
        logging.info(f"- Model: {LOCAL_LLM_MODEL_NAME} via {LOCAL_LLM_BASE_URL}")
        logging.info(f"- Cache file: {self.cache_path}")
        logging.info(f"- Report output directory: {self.output_dir}")
        logging.info(f"- Max concurrent workers: {self.max_workers}")
        if self.force_reanalyze:
            logging.warning("- Caching is OFF. Forcing re-analysis of all files.")

    def _load_prompts(self):
        """Loads prompts from the prompts.json file."""
        try:
            prompts_path = self.script_dir / "prompts.json"
            with open(prompts_path, "r", encoding="utf-8") as f:
                self.prompts = json.load(f)
        except FileNotFoundError:
            logging.error(
                "CRITICAL: `prompts.json` not found. Please create it next to the script."
            )
            raise
        except json.JSONDecodeError:
            logging.error("CRITICAL: `prompts.json` is not valid JSON.")
            raise

    def _load_or_init_cache(self):
        """Loads cache from disk if it exists, otherwise initializes an empty cache in memory."""
        if self.cache_path.exists() and not self.force_reanalyze:
            logging.info(f"Loading existing cache from {self.cache_path}")
            with open(self.cache_path, "r", encoding="utf-8") as f:
                self.cache_data = json.load(f)
        else:
            logging.info("Initializing new cache.")
            self.cache_data = {
                "project_name": self.project_dir.name,
                "directories": {},
                "files": {},
            }

    def _save_cache(self):
        """Saves the in-memory cache to the JSON file on disk."""
        with self.cache_lock:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache_data, f, indent=4)

    def _get_file_hash(self, file_path):
        """Generates a SHA256 hash for a given file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256.update(byte_block)
        return sha256.hexdigest()

    def _count_tokens(self, text: str) -> int:
        """Counts tokens using tiktoken or falls back to a word count approximation."""
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return len(text.split())

    def _call_llm(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        """Makes a call to the LLM and handles potential errors."""
        try:
            message = self.client.chat.completions.create(
                model=LOCAL_LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return message.choices[0].message.content.strip()
        except BadRequestError as e:
            logging.error(
                f"LLM BadRequestError: {e}. Prompt may exceed context window."
            )
            return f"Error: Bad request. Prompt too long. Details: {e}"
        except APIError as e:
            logging.error(f"LLM APIError: {e}")
            return f"Error: API error. Details: {e}"
        except Exception as e:
            logging.error(f"An unexpected error occurred while calling the LLM: {e}")
            return f"Error: Unexpected error. Details: {e}"

    def is_excluded(self, path):
        """Checks if a given path should be excluded from analysis."""
        return any(excluded in Path(path).parts for excluded in EXCLUSION_LIST)

    def _analyze_file(self, file_path):
        """Analyzes a single file, using cache if available, and chunks content if too large."""
        rel_path = str(file_path.relative_to(self.project_dir))

        try:
            # 1. Caching & Hashing (Kept the same for efficiency)
            file_hash = self._get_file_hash(file_path)
            if not self.force_reanalyze:
                cached_file = self.cache_data.get("files", {}).get(rel_path)
                if cached_file and cached_file.get("hash") == file_hash:
                    return  # File is unchanged, skip LLM analysis

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            token_count = self._count_tokens(content)

            # 2. Chunking Logic for Large Files
            final_content_for_llm = content
            system_prompt = self.prompts["file_analysis"]["system"]
            user_prompt_template = self.prompts["file_analysis"]["user"]
            max_tokens_for_final_summary = 4096

            if token_count > CONTEXT_TOKEN_THRESHOLD:
                logging.warning(
                    f"File '{rel_path}' is too large ({token_count} tokens). Performing chunked summarization."
                )

                # Split content into chunks
                # A simple split by large newline separators (or just splitting content tokens)
                # is sufficient for most code files. Using content.split('\n\n') for code files.
                chunks = content.split("\n\n")

                chunk_summaries = []
                current_chunk_parts = []
                current_chunk_tokens = 0

                # MAP Phase: Summarize each manageable chunk
                for part in chunks:
                    part_tokens = self._count_tokens(part)

                    if (
                        current_chunk_tokens + part_tokens > CONTEXT_TOKEN_THRESHOLD / 2
                    ) and current_chunk_parts:
                        # Process current batch if adding new part would exceed half the context
                        chunk_context = "\n\n".join(current_chunk_parts)

                        chunk_prompt_template = self.prompts["file_chunk_summary"]

                        chunk_summary = self._call_llm(
                            chunk_prompt_template["system"],
                            chunk_prompt_template["user"].format(
                                file_path=rel_path, chunk_content=chunk_context
                            ),
                            max_tokens=1024,  # Summarize each chunk into a smaller summary
                        )
                        chunk_summaries.append(chunk_summary)
                        current_chunk_parts, current_chunk_tokens = [], 0

                    current_chunk_parts.append(part)
                    current_chunk_tokens += part_tokens

                if current_chunk_parts:  # Process the last chunk
                    chunk_context = "\n\n".join(current_chunk_parts)
                    chunk_prompt_template = self.prompts["file_chunk_summary"]
                    chunk_summary = self._call_llm(
                        chunk_prompt_template["system"],
                        chunk_prompt_template["user"].format(
                            file_path=rel_path, chunk_content=chunk_context
                        ),
                        max_tokens=1024,
                    )
                    chunk_summaries.append(chunk_summary)

                # REDUCE Phase: Combine chunk summaries for final analysis
                final_content_for_llm = "\n\n".join(
                    [
                        f"--- Chunk Summary {i + 1} ---\n{s}"
                        for i, s in enumerate(chunk_summaries)
                    ]
                )
                system_prompt = self.prompts["file_synthesis"]["system"]
                user_prompt_template = self.prompts["file_synthesis"]["user"]
                max_tokens_for_final_summary = (
                    2048  # Use a smaller max_tokens for the final summary
                )

            # 3. Final LLM Call (Original or Synthesis)
            user_prompt = user_prompt_template.format(
                rel_path=rel_path, content=final_content_for_llm
            )

            summary = self._call_llm(
                system_prompt, user_prompt, max_tokens=max_tokens_for_final_summary
            )
            summary_data = {"summary": summary, "hash": file_hash}

            # Update in-memory cache (thread-safe)
            with self.cache_lock:
                self.cache_data["files"][rel_path] = summary_data

        except Exception as e:
            # Handle potential exceptions during file processing
            logging.error(f"Error analyzing file {rel_path}: {e}")
            with self.cache_lock:
                self.cache_data["files"][rel_path] = {
                    "summary": f"Error: Failed during analysis or chunking. Details: {e}",
                    "hash": file_hash,
                }

    def _analyze_single_directory(self, dir_path):
        """Analyzes a single directory by synthesizing summaries of its contents."""
        rel_path = (
            str(dir_path.relative_to(self.project_dir))
            if dir_path != self.project_dir
            else "."
        )
        logging.info(f"Synthesizing summary for directory: {rel_path}")

        child_items = [
            item for item in dir_path.iterdir() if not self.is_excluded(item)
        ]
        if not child_items:
            summary = "This is an empty directory."
            with self.cache_lock:
                self.cache_data["directories"][rel_path] = summary
            return

        context_parts = []
        for item in child_items:
            item_rel_path = str(item.relative_to(self.project_dir))
            summary = ""
            if item.is_file():
                summary = (
                    self.cache_data.get("files", {})
                    .get(item_rel_path, {})
                    .get("summary")
                )
                if summary:
                    context_parts.append(
                        f"--- Summary of file: {item.name} ---\n{summary}"
                    )
            elif item.is_dir():
                summary = self.cache_data.get("directories", {}).get(item_rel_path)
                if summary:
                    context_parts.append(
                        f"--- Summary of subdirectory: {item.name}/ ---\n{summary}"
                    )

        if not context_parts:
            summary = "Directory contains no analyzed items."
            with self.cache_lock:
                self.cache_data["directories"][rel_path] = summary
            return

        context_str = "\n\n".join(context_parts)

        # --- Map-Reduce for large context ---
        token_count = self._count_tokens(context_str)
        if token_count > CONTEXT_TOKEN_THRESHOLD:
            logging.warning(
                f"Context for '{rel_path}' is too large ({token_count} tokens). Performing chunked summarization."
            )

            # **NEW: Save the full context before reduction**
            safe_rel_path = rel_path.replace("/", "_").replace(".", "ROOT")
            context_save_path = (
                self.output_dir
                / f"FULL_CONTEXT_{safe_rel_path}_{token_count}_tokens.txt"
            )
            with open(context_save_path, "w", encoding="utf-8") as f:
                f.write(context_str)
            logging.info(
                f"Saved full context (pre-reduce) to: {context_save_path.name}"
            )
            # **END NEW BLOCK**

            # MAP: Summarize chunks of the context
            chunk_summaries = []
            current_chunk = []
            current_chunk_tokens = 0

            for part in context_parts:
                part_tokens = self._count_tokens(part)
                if (
                    current_chunk_tokens + part_tokens > CONTEXT_TOKEN_THRESHOLD
                    and current_chunk
                ):
                    chunk_context = "\n\n".join(current_chunk)
                    prompt_template = self.prompts["directory_synthesis_chunk"]
                    chunk_summary = self._call_llm(
                        prompt_template["system"],
                        prompt_template["user"].format(context_str=chunk_context),
                    )
                    chunk_summaries.append(chunk_summary)
                    current_chunk, current_chunk_tokens = [], 0

                current_chunk.append(part)
                current_chunk_tokens += part_tokens

            if current_chunk:  # Process the last chunk
                chunk_context = "\n\n".join(current_chunk)
                prompt_template = self.prompts["directory_synthesis_chunk"]
                chunk_summary = self._call_llm(
                    prompt_template["system"],
                    prompt_template["user"].format(context_str=chunk_context),
                )
                chunk_summaries.append(
                    f"--- Summary of content chunk ---\n{chunk_summary}"
                )

            # REDUCE: Summarize the summaries of the chunks
            context_str = "\n\n".join(chunk_summaries)
            logging.info(
                f"Synthesizing final summary for '{rel_path}' from {len(chunk_summaries)} chunks."
            )

        prompt_template = self.prompts["directory_synthesis"]
        user_prompt = prompt_template["user"].format(
            rel_path=rel_path, context_str=context_str
        )
        final_summary = self._call_llm(
            prompt_template["system"], user_prompt, max_tokens=2048
        )

        with self.cache_lock:
            self.cache_data["directories"][rel_path] = final_summary

    def generate_plain_text_summary(self):
        """
        Exports the entire project analysis into a single, human-readable text file
        suitable for a simple knowledge base or comprehensive documentation.
        """
        logging.info("--- Phase 4: Generating Plain Text Summary File ---")

        output_path = self.output_dir / "project_summary.txt"

        # Determine the order of directories to write (deepest first, then root)
        # This gives a natural flow: deep components -> high-level structure
        sorted_dir_keys = sorted(
            self.cache_data.get("directories", {}).keys(),
            key=lambda k: (1 if k == "." else 0, len(k)),  # Put '.' (root) last
            reverse=True,
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"PROJECT ANALYSIS SUMMARY: {self.project_dir.name}\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            # 1. Directory Summaries (The Architecture)
            f.write("### 1. DIRECTORY AND ARCHITECTURE SUMMARIES ###\n\n")
            for rel_path in sorted_dir_keys:
                summary = self.cache_data["directories"].get(rel_path)
                if (
                    summary
                    and "Error:" not in summary
                    and "empty directory" not in summary
                ):
                    # Use the project name for the root directory '.'
                    title_path = rel_path if rel_path != "." else self.project_dir.name

                    f.write(f"--- DIRECTORY: {title_path} ---\n")
                    f.write(f"{summary.strip()}\n")
                    f.write("-" * 40 + "\n\n")

            f.write("\n" + "=" * 60 + "\n\n")

            # 2. File Summaries (The Details)
            f.write("### 2. INDIVIDUAL FILE SUMMARIES ###\n\n")
            # Sort files alphabetically for easier look-up
            sorted_file_keys = sorted(self.cache_data.get("files", {}).keys())

            for rel_path in sorted_file_keys:
                data = self.cache_data["files"].get(rel_path)
                summary = data.get("summary")

                if summary and "Error:" not in summary:
                    f.write(f"--- FILE: {rel_path} ---\n")
                    f.write(f"{summary.strip()}\n")
                    f.write("-" * 40 + "\n\n")

        logging.info(f"Plain text summary generated at: {output_path}")
        return output_path

    def analyze_project(self):
        """Orchestrates the entire project analysis: files then directories."""
        logging.info("--- Phase 1: Identifying Files to Analyze ---")
        all_files = [
            p
            for p in self.project_dir.rglob("*")
            if p.is_file() and not self.is_excluded(p)
        ]

        files_to_reanalyze = []
        files_to_skip = 0

        # New Pre-filtering Logic
        for file_path in tqdm(all_files, desc="Checking file hashes (Caching)"):
            rel_path = str(file_path.relative_to(self.project_dir))
            try:
                file_hash = self._get_file_hash(file_path)
                cached_file = self.cache_data.get("files", {}).get(rel_path)

                if (
                    not self.force_reanalyze
                    and cached_file
                    and cached_file.get("hash") == file_hash
                ):
                    files_to_skip += 1
                    continue  # File is unchanged, skip analysis

                files_to_reanalyze.append(file_path)
            except Exception as e:
                logging.warning(
                    f"Could not hash file {rel_path}, forcing re-analysis: {e}"
                )
                files_to_reanalyze.append(file_path)

        logging.info(f"Identified {len(all_files)} total files.")
        if files_to_skip > 0:
            logging.info(
                f"Skipping LLM analysis for {files_to_skip} unchanged files (Cache hit)."
            )
        logging.info(
            f"Proceeding to analyze {len(files_to_reanalyze)} files with the LLM."
        )

        logging.info("--- Phase 1.1: Analyzing Modified/New Files with LLM ---")

        # Only run the executor for the files that actually need LLM attention
        if files_to_reanalyze:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                list(
                    tqdm(
                        executor.map(self._analyze_file, files_to_reanalyze),
                        total=len(files_to_reanalyze),
                        desc="Analyzing files (LLM Calls)",
                    )
                )

        logging.info("File analysis complete. Saving cache to disk.")
        self._save_cache()

        # Phase 2 (Directory Analysis) remains the same as it must be sequential (bottom-up)
        logging.info("--- Phase 2: Analyzing Directories (Bottom-Up) ---")
        dirs_to_analyze = [
            p
            for p in self.project_dir.rglob("*")
            if p.is_dir() and not self.is_excluded(p)
        ]
        dirs_to_analyze.sort(key=lambda p: len(p.parts), reverse=True)  # Deepest first

        for dir_path in tqdm(dirs_to_analyze, desc="Analyzing directories"):
            self._analyze_single_directory(dir_path)

        # Analyze the root directory last
        self._analyze_single_directory(self.project_dir)

        logging.info("Directory analysis complete. Saving cache to disk.")
        self._save_cache()
        logging.info("--- Project Analysis Complete ---")

    def generate_rag_documents(self):
        """
        Exports the analysis findings into a JSONL file suitable for RAG ingestion.
        Each line in the file is a JSON object representing a single document (chunk).
        """
        logging.info("--- Phase 3: Generating RAG Documents ---")

        output_path = self.output_dir / "rag_documents.jsonl"
        documents = []

        # Process file summaries
        for rel_path, data in self.cache_data.get("files", {}).items():
            if not data.get("summary") or "Error:" in data.get("summary"):
                continue  # Skip files that failed analysis

            document = {
                "content": data["summary"],
                "metadata": {
                    "source": rel_path,
                    "type": "file",
                    "project_name": self.project_dir.name,
                    "hash": data.get("hash"),
                },
            }
            documents.append(document)

        # Process directory summaries
        for rel_path, summary in self.cache_data.get("directories", {}).items():
            if not summary or "Error:" in summary or "empty directory" in summary:
                continue  # Skip directories that failed or are empty

            document = {
                "content": summary,
                "metadata": {
                    "source": rel_path if rel_path != "." else self.project_dir.name,
                    "type": "directory",
                    "project_name": self.project_dir.name,
                },
            }
            documents.append(document)

        # Write all documents to the JSONL file
        with open(output_path, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc) + "\n")

        logging.info(f"{len(documents)} documents for RAG generated at: {output_path}")
        return output_path

    def finalize(self):
        """Copies final cache to the output directory for archival."""
        final_cache_path = self.output_dir / "findings.json"
        with open(self.cache_path, "rb") as f_src:
            with open(final_cache_path, "wb") as f_dst:
                f_dst.write(f_src.read())
        logging.info(f"Copied final findings to {final_cache_path}")
        return final_cache_path


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a project with concurrent, cached, hierarchical summarization."
    )
    parser.add_argument(
        "project_directory",
        nargs="?",
        default=".",
        help="Path to the project directory. Defaults to current directory.",
    )
    parser.add_argument(
        "--force-reanalyze",
        action="store_true",
        help="Force re-analysis of all files, ignoring the cache.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Max concurrent workers for API calls (default: {MAX_WORKERS}).",
    )
    args = parser.parse_args()

    try:
        analyzer = ProjectAnalyzer(
            project_dir=args.project_directory,
            force_reanalyze=args.force_reanalyze,
            max_workers=args.max_workers,
        )
        analyzer.analyze_project()

        # Call the new method to generate the plain text summary
        plain_text_path = analyzer.generate_plain_text_summary()

        rag_docs_path = analyzer.generate_rag_documents()
        final_findings_path = analyzer.finalize()

        logging.info(
            f"\n--- All tasks complete! ---\n"
            f"Results saved to directory: {analyzer.output_dir.resolve()}\n"
            f"  - Plain Text Summary: {plain_text_path.resolve()}\n"  # NEW LOG ENTRY
            f"  - RAG Documents: {rag_docs_path.resolve()}\n"
            f"  - Full JSON Findings: {final_findings_path.resolve()}\n"
            f"Cache for future runs is stored at: {analyzer.cache_path.resolve()}"
        )
    except Exception as e:
        logging.error(f"A critical error occurred in main: {e}", exc_info=True)


if __name__ == "__main__":
    main()
