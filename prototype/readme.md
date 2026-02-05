# AI-Powered Hierarchical Project Analyzer

This tool leverages Large Language Models (LLMs) to perform a deep, hierarchical analysis of a software project's codebase. It starts by summarizing individual files and then works its way up, creating synthetic summaries for each directory based on the contents within. The result is a multi-layered understanding of the project's architecture, from a single file's purpose to a high-level overview of the entire repository.

This is ideal for quickly onboarding new developers, understanding legacy code, or generating structured data about a project for use in Retrieval-Augmented Generation (RAG) systems.

## Key Features

- **Hierarchical Summarization**: Creates summaries for not just files, but for every directory, providing a bottom-up understanding of the codebase.
- **Local LLM Integration**: Connects to any OpenAI-compatible API endpoint, making it perfect for use with local models via tools like Ollama, vLLM, or LM Studio.
- **Intelligent Caching**: Hashes files to avoid re-analyzing anything that hasn't changed between runs, saving time and API calls.
- **Concurrent Processing**: Analyzes multiple files simultaneously using a thread pool to speed up the initial analysis phase.
- **Handles Large Contexts**: Automatically employs a map-reduce strategy to summarize directories with content that would otherwise exceed the LLM's context window.
- **RAG-Ready Output**: Generates a `.jsonl` file where each line is a JSON object containing a summary (a "document chunk") and associated metadata, perfect for ingesting into a vector database.
- **Configurable Exclusions**: Easily ignore common directories and files (like `.git`, `node_modules`, etc.) to focus the analysis on relevant source code.

## How It Works

The script operates in a series of distinct phases to build its understanding of the project.

1. **Phase 1: File Analysis**

      - The script recursively scans the target project for all files, skipping any paths defined in the `EXCLUSION_LIST`.
      - Using a thread pool, it sends the content of each file to the LLM for analysis based on the `file_analysis` prompt.
      - Before analysis, it checks the cache. If a file with the same content (verified by a SHA256 hash) has already been analyzed, it skips the LLM call and uses the cached summary.
      - Results are stored in an in-memory cache and saved to disk upon completion of this phase.

2. **Phase 2: Directory Synthesis (Bottom-Up)**

      - The script identifies all directories and sorts them from the deepest to the shallowest (the root).
      - For each directory, it collects the cached summaries of its immediate children (both files and subdirectories).
      - It then sends this collection of summaries to the LLM using the `directory_synthesis` prompt to create a single, cohesive summary for the parent directory.
      - If the collected summaries are too large for the LLM's context window, it first "maps" over chunks of the summaries using the `directory_synthesis_chunk` prompt and then "reduces" those intermediate summaries into a final one.
      - This new directory summary is then cached. The process repeats, moving up the hierarchy until the root directory is summarized.

3. **Phase 3: RAG Document Generation**

      - After all analysis is complete, the script iterates through the final cache.
      - It formats every file summary and directory summary into a structured JSON object.
      - These objects are written to a `rag_documents.jsonl` file, one per line.

4. **Finalization**

      - A complete copy of the cache from the run, `findings.json`, is saved to the timestamped output folder for archival and review.

## Project File Structure

To use the script, your files should be arranged as follows:

```struct
your-project-folder/
├── hierarchical_summarization.py
└── prompts.json
```

## Prerequisites

- Python 3.12+
- An accessible OpenAI-compatible API endpoint (e.g., a running Ollama server).

## Configuration

The script is configured through environment variables and a constant within the file.

### Environment Variables

- `LOCAL_LLM_BASE_URL`: The base URL of your OpenAI-compatible LLM server. (Default: `http://localhost:11434/v1`)
- `LOCAL_LLM_MODEL_NAME`: The name of the model you want to use for analysis. (Default: `deepseek-r1:14b`)
- `MAX_WORKERS`: The number of concurrent threads to use for file analysis. (Default: `10`)

### Script Constants

- `EXCLUSION_LIST`: A Python list at the top of the script where you can add file or directory names to be ignored during analysis.

## Usage

Run the script from your terminal.

- **Analyze the current directory:**

    ```bash
    python hierarchical_summarization.py
    ```

- **Analyze a specific project directory:**

    ```bash
    python hierarchical_summarization.py /path/to/your/project
    ```

- **Force a full re-analysis, ignoring the cache:**

    ```bash
    python hierarchical_summarization.py --force-reanalyze
    ```

- **Adjust the number of concurrent workers:**

    ```bash
    python hierarchical_summarization.py --max-workers 5
    ```

## The `prompts.json` File

This file is central to the tool's behavior, allowing you to customize the instructions given to the LLM for different tasks.

- `file_analysis`: Used to generate the summary for a single source code file. It asks for the file's purpose, a breakdown of its components, and its interactions.
- `directory_synthesis`: Used to create a high-level summary of a directory from the summaries of its contents. It instructs the LLM to synthesize a cohesive overview.
- `directory_synthesis_chunk`: A helper prompt used in the map-reduce process. It condenses a "chunk" of summaries into an intermediate paragraph when the context for a directory is too large.
- `developer_guide`: **(For Future Use)** This prompt is designed to generate a full developer onboarding guide from the project's root summary and top-level component summaries. *Note: The provided Python script does not currently have the logic to execute this prompt, but it is available for future extension.*

## Output

All results are saved in a `findings` directory, which is created where the script is run.

```struct
findings/
└── your_project_name_YYYYMMDD_HHMMSS/
    ├── rag_documents.jsonl
    └── findings.json
```

- `findings/your_project_name_<timestamp>/`: A unique directory created for each run.
- `rag_documents.jsonl`: The final, clean output ready for RAG ingestion. Each line is a self-contained JSON document.
- `findings.json`: A full, raw dump of the cache generated during the run, including file hashes and hierarchical summaries. This is a complete record of the analysis.
- `.project_analyzer_cache` directory is also created to persist the cache between runs.
