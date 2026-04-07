# Local LLM Codebase Analyzer

A local-first tool that uses Ollama to analyze a software project — scanning 
every file and directory, generating structured summaries, and producing a 
clean Markdown knowledge base you can actually use.

Built for the "discovery" phase: when you're dropped into an unfamiliar 
codebase and need to understand it fast. Works well for documentation, 
onboarding, or as a RAG knowledge source.

## What it does

- Recursively scans a project directory and analyzes each file individually
- Identifies classes, functions, key variables, and overall purpose per file
- Summarizes directories bottom-up using the file summaries as context
- Combines everything into a single, readable Markdown knowledge base
- SHA256-based caching — only re-analyzes files that have actually changed
- Handles large projects by summarizing summaries if context window is exceeded
- Everything runs locally via Ollama. Your code never leaves your machine.

---

## How it works

1. Root scan — gets a high-level picture of the project structure and language
2. File analysis — walks every file, checks the cache, sends changed files 
   to the LLM for structured analysis
3. Directory analysis — works bottom-up, using file summaries as context 
   for each directory
4. Knowledge base generation — combines all summaries into one clean 
   Markdown document

---

## Getting started

### Requirements

- Python 3.7+
- Ollama installed and running
```bash
# Default model (small and fast)
ollama pull opencoder:1.5b

# Alternatives if you want more accuracy
ollama pull codellama:7b
ollama pull deepseek-coder:6.7b
```

### Install
```bash
git clone https://github.com/kamalpandi/RAG_code_analyzer.git
cd RAG_code_analyzer
pip install openai tqdm tiktoken
```

---

## Usage
```bash
# Analyze current directory
python project_analyzer.py

# Analyze a specific path
python project_analyzer.py /path/to/your/project

# Force re-analysis (ignore cache)
python project_analyzer.py --force-reanalyze
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `LOCAL_LLM_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `LOCAL_LLM_MODEL_NAME` | `opencoder:1.5b` | Model to use |

---

## Output

Each run creates a timestamped folder inside `findings/`:
```
findings/
└── 20251021_120533/
├── findings.json          # Raw summaries and file hashes (the cache)
├── initial-summaries.txt  # Streaming log, useful for debugging
└── knowledge_base.md      # The final document — this is what you want
```
---

## Tech stack

- Python, Ollama (local OpenAI-compatible API)
- openai, tqdm, tiktoken
- uv for package management

---

## Planned

- Async indexing with Celery + Redis for large projects
- Diff view to show what the agent changed
- Support for Jupyter notebooks and docs
- Simple web UI to browse the knowledge base
