import os
import openai
import logging
import json
import argparse
import hashlib
import tiktoken

from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from openai import APIError, BadRequestError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
LOCAL_LLM_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL_NAME", "opencoder:1.5b")


# Exclusion list
EXCLUSION_LIST = [
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".DS_Store",
    "pb_data",
    "pb_public",
    "migrations",
]


class ProjectAnalyzer:
    def __init__(self, project_dir, force_reanalyze=False):
        self.project_dir = Path(project_dir)
        self.script_dir = Path(__file__).parent
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.force_reanalyze = force_reanalyze
        self.findings_dir = self.script_dir / "findings" / self.timestamp
        self.findings_dir.mkdir(parents=True, exist_ok=True)
        self.findings_path = self.findings_dir / "findings.json"
        self.initial_summaries_path = (
            self.script_dir / f"initial-summaries_{self.timestamp}.txt"
        )
        BASE_URL_WITH_V1 = LOCAL_LLM_BASE_URL + "/v1"
        self.client = openai.OpenAI(base_url=BASE_URL_WITH_V1, api_key="not-needed")
        self._init_findings_file()
        logging.info("Initialized ProjectAnalyzer:")
        logging.info(f"- Project directory: {self.project_dir}")
        logging.info(f"- Using model: {LOCAL_LLM_MODEL_NAME} via {LOCAL_LLM_BASE_URL}")
        logging.info(f"- Findings directory: {self.findings_dir}")
        if self.force_reanalyze:
            logging.warning("- Caching is disabled. Forcing re-analysis of all files.")

    def _get_file_hash(self, file_path):
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()

    def _count_tokens(self, text: str) -> int:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            # Fallback for models not using cl100k_base
            return len(text.split())

    def _call_llm(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        try:
            # Note: max_tokens for the *response* is different from the model's context window
            message = self.client.chat.completions.create(
                model=LOCAL_LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
            )
            return message.choices[0].message.content.strip()
        except BadRequestError as e:
            logging.error(f"LLM BadRequestError: {e}.")
            return f"Error: The model reported a bad request. Details: {e}"
        except APIError as e:
            logging.error(f"LLM APIError: {e}")
            return f"Error: The model API returned an error. Details: {e}"
        except Exception as e:
            logging.error(f"An unexpected error occurred while calling the LLM: {e}")
            return f"Error: Could not get a response from the LLM. Details: {e}"

    def _init_findings_file(self):
        self._write_findings({"root_summary": "", "directories": {}, "files": {}})

    def _write_findings(self, data):
        with open(self.findings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _append_to_summaries(self, content):
        with open(self.initial_summaries_path, "a", encoding="utf-8") as f:
            f.write(f"{content}\n\n")

    def _read_findings(self):
        with open(self.findings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _update_findings(self, key, value):
        findings = self._read_findings()
        if isinstance(key, tuple):
            current = findings
            for k in key[:-1]:
                current = current.setdefault(k, {})
            current[key[-1]] = value
        else:
            findings[key] = value
        self._write_findings(findings)

    def is_excluded(self, path):
        path_obj = Path(path)
        return any(excluded in path_obj.as_posix() for excluded in EXCLUSION_LIST)

    def analyze_root(self):
        logging.info("Analyzing root directory...")
        root_contents = [
            str(f.relative_to(self.project_dir))
            for f in self.project_dir.rglob("*")
            if not self.is_excluded(f)
        ]
        root_contents_str = "\n".join(root_contents)
        system_prompt = "You are an AI assistant that summarizes the main language and purpose of a project based on its file structure."
        user_prompt = (
            f"Project directory: {self.project_dir}\n\nFiles and directories:\n{root_contents_str}\n\n"
            "Based on the directory structure and file names, what is the main language used in this project? "
            "What is the project's purpose? Please provide a comprehensive summary."
        )
        summary = self._call_llm(system_prompt, user_prompt, max_tokens=1000)
        self._update_findings("root_summary", summary)
        self._append_to_summaries(f"Project Overview:\n{summary}")
        logging.info("Root analysis complete.")

    def analyze_file(self, file_path):
        rel_path = str(Path(file_path).relative_to(self.project_dir))
        try:
            file_hash = self._get_file_hash(file_path)
            findings = self._read_findings()
            if not self.force_reanalyze:
                cached_file_data = findings.get("files", {}).get(rel_path)
                if (
                    cached_file_data
                    and cached_file_data.get("hash") == file_hash
                    and not cached_file_data.get("summary", "").startswith("Error:")
                ):
                    return cached_file_data.get("summary")

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            system_prompt = "You are an expert AI assistant tasked with analyzing source code and providing a clear, structured summary in plain English."
            user_prompt = f"""
Your task is to analyze the source code file provided below. Read the code carefully and generate a detailed summary.
**File Path:** {rel_path}
**File Content:**
{content}
**Instructions:**
Based on the code content, provide a detailed analysis. Structure your response *exactly* as follows, using these specific headings:
**Overall Purpose:**
(Describe the file's main goal and what it contributes to the project.)
**Classes:**
(List each class in the file. For each class, describe its purpose and significance.)
**Functions/Methods:**
(List each function or method. For each one, describe its purpose, inputs, and what it returns.)
**Key Variables/Fields:**
(Describe any important module-level variables or class instance variables (`self.variable`) and their purpose.)
**Project Context:**
(Explain how this file likely interacts with other parts of the project.)
Do not write any code. Analyze the code provided and generate only the descriptive text summary as requested.
"""
            summary = self._call_llm(system_prompt, user_prompt, max_tokens=2048)
            summary_data = {"summary": summary, "hash": file_hash}
            self._update_findings(("files", rel_path), summary_data)
            self._append_to_summaries(f"File: {rel_path}\n{summary}")
            return summary
        except Exception as e:
            logging.error(f"Error analyzing file {file_path}: {str(e)}")
            error_summary = f"Error analyzing this file. Details: {str(e)}"
            summary_data = {"summary": error_summary, "hash": "error"}
            self._update_findings(("files", rel_path), summary_data)
            return None

    def analyze_directory(self, dir_path):
        if self.is_excluded(dir_path):
            return

        rel_path = str(Path(dir_path).relative_to(self.project_dir))
        if rel_path == ".":
            return

        try:
            contents = [
                item.name
                for item in Path(dir_path).iterdir()
                if not self.is_excluded(item)
            ]
            if not contents:
                return

            findings = self._read_findings()
            file_summaries = []
            for item in contents:
                item_rel_path = str(Path(rel_path) / item)
                if item_rel_path in findings.get("files", {}):
                    summary_text = findings["files"][item_rel_path].get(
                        "summary", "No summary available."
                    )
                    # Get the first line of the "Overall Purpose" section
                    first_line = "No purpose defined."
                    for line in summary_text.splitlines():
                        if "overall purpose" in line.lower():
                            first_line = summary_text.splitlines()[1]
                            break
                    file_summaries.append(f"- {item}: {first_line}")

            file_summaries_str = "\n".join(file_summaries)
            system_prompt = "You are an AI assistant that analyzes code directories."
            user_prompt = (
                f"Analyze the purpose of this directory: '{rel_path}'\n\n"
                f"It contains the following files and subdirectories:\n{', '.join(contents)}\n\n"
                f"Here are one-line summaries of the files I have analyzed inside it:\n{file_summaries_str}\n\n"
                "Please provide a summary of this directory's purpose and how its contents work together."
            )
            summary = self._call_llm(system_prompt, user_prompt, max_tokens=1000)
            self._update_findings(("directories", rel_path), summary)
            self._append_to_summaries(f"Directory: {rel_path}\n{summary}")
        except Exception as e:
            logging.error(f"Error analyzing directory {dir_path}: {str(e)}")

    def analyze_project(self):
        logging.info(f"Starting analysis of project: {self.project_dir}")
        files_to_analyze = []
        dirs_to_analyze = []
        for root, dirs, files in os.walk(self.project_dir, topdown=True):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if not self.is_excluded(Path(root) / d)]

            # Add directories for analysis (after pruning)
            for d in dirs:
                dirs_to_analyze.append(Path(root) / d)

            # Add files for analysis
            for name in files:
                file_path = Path(root) / name
                if not self.is_excluded(file_path):
                    files_to_analyze.append(str(file_path))

        self.analyze_root()

        logging.info(f"Found {len(files_to_analyze)} files to analyze.")
        for file_path in tqdm(files_to_analyze, desc="Analyzing files"):
            self.analyze_file(file_path)

        logging.info(f"Found {len(dirs_to_analyze)} directories to analyze.")
        # Analyze directories in reverse order (from deepest to shallowest)
        for dir_path in tqdm(
            sorted(dirs_to_analyze, key=lambda p: -len(p.parts)),
            desc="Analyzing directories",
        ):
            self.analyze_directory(dir_path)

        logging.info("Project analysis complete.")
        return self.initial_summaries_path, self.findings_path

    def _get_high_level_summary(self, all_summaries: str) -> str:
        logging.info("Synthesizing a high-level summary from all findings...")
        system_prompt = (
            "You are a senior software architect. Your task is to read a collection of detailed file and directory "
            "summaries and produce a single, high-level, synthesized overview of the entire project. Focus on the "
            "architecture, key components, and how they interact. Ignore minor details and focus on the big picture."
        )
        user_prompt = f"Here are the detailed summaries of a project's files and directories:\n\n{all_summaries}\n\n---\n\nNow, provide a high-level architectural summary of the entire project based on this information."
        return self._call_llm(system_prompt, user_prompt, max_tokens=2048)

    def generate_knowledge_base(self):
        logging.info("Generating structured knowledge base for chatbot...")
        with open(self.findings_path, "r", encoding="utf-8") as f:
            findings_data = json.load(f)
        root_summary = findings_data.get("root_summary", "")
        dir_summaries = "\n\n".join(
            f"Directory: {path}\nSummary:\n{summary}"
            for path, summary in findings_data.get("directories", {}).items()
        )
        file_summaries = "\n\n".join(
            f"File: {path}\nAnalysis:\n{data.get('summary', 'No summary.')}"
            for path, data in findings_data.get("files", {}).items()
        )
        all_summaries = (
            f"Project Overview:\n{root_summary}\n\n{dir_summaries}\n\n{file_summaries}"
        )

        token_count = self._count_tokens(all_summaries)

        # UPDATED: Realistic token threshold for a 16k model
        token_threshold = 14000
        logging.info(f"Total summary token count for KB generation: {token_count}")

        if token_count > token_threshold:
            logging.warning(
                f"Token count ({token_count}) exceeds threshold of {token_threshold}. "
                "Generating high-level summary first to reduce context size."
            )
            context_for_kb = self._get_high_level_summary(all_summaries)
        else:
            logging.info(
                "Token count is within limits. Using full analysis for knowledge base."
            )
            context_for_kb = all_summaries

        # ADDED: Debugging log to see the final context
        logging.info(
            f"Final context character count for KB generation: {len(context_for_kb)}"
        )

        # UPDATED: New, more robust prompts for the final generation step
        system_prompt = """
You are an expert technical writer AI. Your only task is to reformat a provided text analysis into a structured Markdown knowledge base.
You must follow the user's formatting rules precisely.
Do NOT add any commentary, introductions, or extra text.
Do NOT generate code. Your job is to format the given text.
"""
        user_prompt = f"""
I will provide you with a raw analysis of a codebase. Reformat this analysis into a structured Markdown document.

**REQUIRED OUTPUT FORMAT EXAMPLE:**
---
# Project: Example Web App
## Project Overview
This project is a Python-based web server using Flask. Its main goal is to provide a REST API for user management.

## Directory: src/routes
This directory contains all the API route definitions for the project.

## File: src/routes/user_routes.py
### Purpose
This file defines the endpoints related to user creation and login.
### Key Components (Classes/Functions)
- `create_user()`: A function that handles the POST request to /users.
- `login()`: A function that handles user authentication.
### Role in Project
This is the primary interface for all user-related interactions in the application.
---

**ACTUAL ANALYSIS CONTENT TO REFORMAT:**
---
{context_for_kb}
---

Now, apply the format shown in the example to the analysis content provided above.
"""
        # Using a larger max_tokens for the final output since the input context is large
        kb_content = self._call_llm(system_prompt, user_prompt, max_tokens=8192)
        kb_path = self.findings_dir / "knowledge_base.md"
        with open(kb_path, "w", encoding="utf-8") as f:
            f.write(kb_content)
        logging.info(f"Knowledge Base generated: {kb_path}")
        return kb_path


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a software project using a local LLM and generate a knowledge base for a chatbot."
    )
    parser.add_argument(
        "project_directory",
        nargs="?",
        default=".",
        help="The path to the project directory to analyze. Defaults to the current directory.",
    )
    parser.add_argument(
        "--force-reanalyze",
        action="store_true",
        help="Force the script to re-analyze all files, ignoring any cached results.",
    )
    args = parser.parse_args()
    project_dir = Path(args.project_directory).resolve()
    if not project_dir.is_dir():
        logging.error(f"Project directory '{project_dir}' not found.")
        return

    analyzer = ProjectAnalyzer(project_dir, force_reanalyze=args.force_reanalyze)
    initial_summaries_path, findings_path = analyzer.analyze_project()
    kb_path = analyzer.generate_knowledge_base()
    logging.info(
        f"\n--- All tasks complete! ---\n"
        f"Results saved to directory: {analyzer.findings_dir.resolve()}\n"
        f"  - Initial Summaries: {initial_summaries_path.resolve()}\n"
        f"  - JSON Findings: {findings_path.resolve()}\n"
        f"  - Chatbot Knowledge Base: {kb_path.resolve()}"
    )


if __name__ == "__main__":
    main()
