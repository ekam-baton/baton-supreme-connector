"""
Baton Supreme Connector — Skills Loader
Loads skill markdown files from the /skills directory and injects them
into the agent's system prompt. Users can drop .md files to add capabilities.
"""

import os
from typing import List, Dict

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")


def load_all_skills() -> List[Dict[str, str]]:
    """Loads all .md files from the skills directory."""
    skills = []
    if not os.path.exists(SKILLS_DIR):
        os.makedirs(SKILLS_DIR, exist_ok=True)
        # Create a sample skill
        sample_path = os.path.join(SKILLS_DIR, "example_summarizer.md")
        if not os.path.exists(sample_path):
            with open(sample_path, "w", encoding="utf-8") as f:
                f.write("""---
name: Web Summarizer
description: Summarize any webpage into bullet points
---

# Web Summarizer Skill

When the user asks you to summarize a webpage:
1. Use the `fetch_url` tool to get the page content
2. Extract the key points
3. Present them as concise bullet points
4. Include the source URL at the bottom
""")

    for fname in os.listdir(SKILLS_DIR):
        if fname.endswith(".md"):
            fpath = os.path.join(SKILLS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                skills.append({
                    "filename": fname,
                    "content": content,
                    "path": fpath,
                })
            except Exception:
                continue
    return skills


def get_skills_prompt() -> str:
    """Returns all skills formatted for injection into the system prompt."""
    skills = load_all_skills()
    if not skills:
        return ""

    parts = ["[LOADED SKILLS]"]
    for skill in skills:
        parts.append(f"\n--- Skill: {skill['filename']} ---")
        parts.append(skill["content"][:2000])  # Cap per skill
    parts.append("[END SKILLS]")
    return "\n".join(parts)


def list_skills() -> List[dict]:
    """Returns metadata about all available skills."""
    skills = load_all_skills()
    result = []
    for s in skills:
        # Try to extract name from YAML frontmatter
        name = s["filename"].replace(".md", "").replace("_", " ").title()
        desc = ""
        lines = s["content"].split("\n")
        for line in lines:
            if line.strip().startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.strip().startswith("description:"):
                desc = line.split(":", 1)[1].strip()
        result.append({
            "filename": s["filename"],
            "name": name,
            "description": desc,
            "size_bytes": len(s["content"]),
        })
    return result
