# ===========================================================================
# This folder is the "toolbox" the assistant uses to answer questions about
# residents from the database. Each file here is one specialized tool — one
# finds the person's name, one checks health numbers, one keeps the database
# safe, and so on. The main file (app/retrievers/sql_retriever.py) picks up
# these tools and uses them together.
# ===========================================================================
"""Internal building blocks for the sql_retriever module.

These submodules hold pure (no DB/LLM) helpers split out of sql_retriever.py
for maintainability. The public API and all DB/LLM-executing code stay in
app/retrievers/sql_retriever.py, which re-exports the names defined here.
"""
