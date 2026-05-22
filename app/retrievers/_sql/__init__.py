"""Internal building blocks for the sql_retriever module.

These submodules hold pure (no DB/LLM) helpers split out of sql_retriever.py
for maintainability. The public API and all DB/LLM-executing code stay in
app/retrievers/sql_retriever.py, which re-exports the names defined here.
"""
