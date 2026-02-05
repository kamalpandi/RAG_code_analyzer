# 🤖 Local LLM Codebase Analyzer

This Python script uses a local LLM (like Ollama) to perform a comprehensive analysis of a software project. It recursively scans a directory, analyzes each file and sub-directory, and synthesizes its findings into a structured Markdown knowledge base.

The goal is to automate the "discovery" phase of understanding a new codebase, providing a high-level overview and detailed summaries that can be used for documentation, onboarding, or as context for a retrieval-augmented generation (RAG) chatbot.

## ✨ Key Features

- **Local-First AI:** Leverages a local, OpenAI-compatible API (defaults to Ollama at `http://localhost:11434`). Your code never leaves your machine.
- **Comprehensive Analysis:** Generates summaries for the entire project, each directory, and each individual file.
- **Structured File Summaries:** For each file, it identifies:
  - Overall Purpose
  - Classes
  - Functions/Methods
  - Key Variables
  - Project Context
- **Intelligent Caching:** Caches file analyses using a SHA256 hash. The script will only re-analyze files that have changed, saving significant time and compute.
- **Forced Re-analysis:** A `--force-reanalyze` flag is available to bypass the cache and analyze all files from scratch.
- **Structured Output:** Generates multiple outputs:
  - `findings.json`: A detailed JSON file with all raw analysis data.
  - `initial-summaries.txt`: A human-readable text file containing the streaming log of all summaries.
  - `knowledge_base.md`: A final, clean, and structured Markdown document perfect for a team wiki.
- **Large Project Handling:** If the total analysis is too large for the LLM's context window, it will first generate a high-level summary of the summaries to ensure the final knowledge base can be created.

---

## ⚙️ How It Works

1.  **Root Scan:** The script first performs a high-level scan of the entire project's file and directory structure to determine the main language and overall purpose.
2.  **File Analysis:** It then walks through every file (respecting the `EXCLUSION_LIST`).
    - It calculates the file's SHA256 hash.
    - If the hash matches a cached version (and `--force-reanalyze` is not set), it skips the file.
    - Otherwise, it sends the file's content to the local LLM with a detailed prompt asking for a structured analysis.
    - The summary and hash are saved to `findings.json`.
3.  **Directory Analysis:** After analyzing files, it analyzes directories from the deepest to the shallowest. It provides the LLM with the list of files in that directory and their one-line summaries (pulled from the file analysis) to generate a purpose summary for the directory.
4.  **Knowledge Base Generation:** Finally, it combines the root summary, all directory summaries, and all file summaries into one large text. It sends this to the LLM one last time with a prompt to reformat it all into a clean, easy-to-read Markdown document.

---

## 🚀 Getting Started

### Prerequisites

1.  **Python 3.7+**
2.  **A running Local LLM Server:** This script is configured to work with any OpenAI-compatible API. The default is **Ollama**.

    - [Install Ollama](https://ollama.com/)
    - Pull a model. The script defaults to `opencoder:1.5b`, which is small and fast. You can also use larger, more powerful models.
    <!-- end list -->

    ```bash
    # Pull the default model
    ollama pull opencoder:1.5b

    # Or pull a more powerful alternative
    ollama pull codellama:7b
    ollama pull deepseek-coder:6.7b
    ```

    - Ensure Ollama is running in the background.

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```

2.  **Create a `requirements.txt` file:**
    Create a file named `requirements.txt` and add the following Python libraries:

    ```
    openai
    tqdm
    tiktoken
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

---

## 🏃 Usage

You can run the script from your terminal.

### Basic Usage

To analyze the current directory (`.`) using the default settings:

```bash
python your_script_name.py
```

To analyze a specific project directory:

```bash
python your_script_name.py /path/to/your/project
```

### Options

- `--force-reanalyze`: Force the script to re-analyze all files, even if they are in the cache.
  ```bash
  python your_script_name.py --force-reanalyze
  ```

### Configuration

You can configure the script using environment variables or by editing the file directly.

**Environment Variables:**

- `LOCAL_LLM_BASE_URL`: The base URL of your local LLM's API.
  - **Default:** `http://localhost:11434`
- `LOCAL_LLM_MODEL_NAME`: The name of the model you want to use (e.g., `opencoder:1.5b`, `codellama:7b`).
  - **Default:** `opencoder:1.5b`

**Example:**

```bash
# Example of running with a different model
export LOCAL_LLM_MODEL_NAME="codellama:7b"
python your_script_name.py /path/to/your/project
```

**In-Script Configuration:**

- `EXCLUSION_LIST`: You can add or remove directory and file names from this list at the top of the script to customize what gets ignored during the scan.

---

## 📄 Output

All outputs are saved in a new directory named `findings/` created in the same directory where the script is located. A new timestamped sub-directory is created for each run.

```
your-script-directory/
├── findings/
│   └── 20251021_120533/  <-- Timestamped run
│       ├── findings.json
│       ├── initial-summaries.txt
│       └── knowledge_base.md
└── your_script_name.py
```

- **`findings.json`**: A complete JSON object containing all raw summaries and file hashes. This is the script's "memory" or "cache."
- **`initial-summaries.txt`**: A simple text file that logs all summaries as they are generated. Good for debugging or a quick read.
- **`knowledge_base.md`**: The final, polished Markdown document. This is the most useful file for reading and sharing.

---

## Disclaimer 
The above document/readme.md is created using AI i'm lazy...