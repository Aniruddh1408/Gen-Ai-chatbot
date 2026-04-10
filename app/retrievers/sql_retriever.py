"""
SQL Retriever — Text-to-SQL pipeline with English synthesis.
"""
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm.client import llm, get_system_prompt
from app.schema.schema import SCHEMA, schema_to_text
from app.core.db import run_query
from app.core.logger import get_logger

logger = get_logger("sql_retriever")

# 1. Plan Generation
_plan_prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    ("human", "{query}"),
])
_plan_chain = _plan_prompt | llm | StrOutputParser()

# 2. Results Synthesis
_synthesis_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a Clinical Data Summarizer. 
The following data was SUCCESSFULLY retrieved from the internal clinical database. 
Your task is to summarize this data for the attending physician.

STRICT RULES:
1. NEVER say you don't have access to data; the data is provided below.
2. If the 'Data' is empty [], say: 'No matching records found for this resident.'
3. Be professional, clinical, and concise.
4. If asked about a resident, always include their name if present in the data."""),
    ("human", "User Query: {query}\nRetrieved Database Data: {results}\nProfessional Summary:"),
])
_synthesis_chain = _synthesis_prompt | llm | StrOutputParser()

def build_sql(plan: dict) -> tuple[str, list]:
    table = plan.get("table", "device_status")
    column = plan.get("column", "*")
    order_by = plan.get("order_by")
    
    # 1. CLEAN ORDER BY: Strip existing ASC/DESC to prevent 'DESC DESC' errors
    if order_by:
        order_by = order_by.upper().replace(" DESC", "").replace(" ASC", "").strip()

    # Strict validation of direction
    raw_dir = str(plan.get("order_direction", "ASC")).upper()
    order_dir = "DESC" if "DESC" in raw_dir else "ASC"
    
    limit = plan.get("limit", 10)
    
    # Handle auto-join for resident names
    from_clause = table
    if "residents." in column or any("residents." in str(f.get("column", "")) for f in plan.get("filters", [])):
        if table != "residents":
            from_clause = f"{table} JOIN residents ON {table}.resident_id = residents.id"

    sql = f"SELECT {column} FROM {from_clause}"
    
    conditions = []
    params = []
    for f in plan.get("filters", []):
        col = f.get("column")
        op = f.get("operator", "=")
        val = f.get("value")
        if col and val is not None:
            # 2. IMPROVEMENT: Use ILIKE for case-insensitive name matching
            if "name" in col.lower() and op == "=":
                conditions.append(f"{col} ILIKE %s")
            else:
                conditions.append(f"{col} {op} %s")
            params.append(val)
            
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if order_by:
        sql += f" ORDER BY {order_by} {order_dir}"
    sql += f" LIMIT {limit}"
    
    return sql, params

def handle_sql(query: str) -> dict:
    try:
        # Step 1: Generate & Parse Plan
        plan_str = _plan_chain.invoke({"system_prompt": get_system_prompt(), "query": query}).strip()
        
        if not plan_str:
             raise ValueError("Planner returned an empty response.")

        # Strip markdown if present
        if "```" in plan_str:
            parts = plan_str.split("```")
            plan_str = parts[1] if len(parts) > 1 else parts[0]
            if plan_str.startswith("json"): plan_str = plan_str[4:]
        
        try:
            plan = json.loads(plan_str.strip())
        except json.JSONDecodeError as je:
            logger.error(f"JSON Parse failed on: {plan_str}")
            # FALLBACK: Try to extract anything between { }
            if "{" in plan_str and "}" in plan_str:
                start = plan_str.find("{")
                end = plan_str.rfind("}") + 1
                plan = json.loads(plan_str[start:end])
            else:
                raise ValueError("The AI got confused and failed to generate a valid data plan for this query.")

        logger.info(f"SQL Plan Generated: {plan}")
        
        # Step 2: Build & Execute SQL
        sql, params = build_sql(plan)
        logger.info(f"SQL Query Built: {sql} | Params: {params}")
        result = run_query(sql, params)
        logger.info(f"Query Result: {result}")
        
        # Step 3: English Synthesis
        # OPTIMIZATION: If result is empty, skip LLM synthesis for speed
        if not result:
            return {
                "query": query,
                "plan": plan,
                "sql": sql,
                "result": result,
                "answer": f"I couldn't find any clinical records matching '{query}' in the database."
            }

        answer = _synthesis_chain.invoke({"query": query, "results": str(result)})
        
        return {
            "query": query,
            "plan": plan,
            "sql": sql,
            "result": result,
            "answer": answer
        }
    except Exception as e:
        logger.error(f"SQL Pipeline error: {e}")
        return {"error": str(e), "answer": "I encountered a technical error while analyzing that request."}