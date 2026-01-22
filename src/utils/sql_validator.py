import re
import sqlparse
from sqlparse.tokens import DML, Keyword, Whitespace, Comment
from src.utils.logger import logger

# Set of potentially dangerous SQL keywords to block
DANGEROUS_KEYWORDS = {
    'DROP', 'INSERT', 'UPDATE', 'DELETE', 'ALTER',
    'CREATE', 'EXEC', 'MERGE', 'TRUNCATE', 'REPLACE'
}


def extract_sql_query(full_text: str) -> str:
    """
    Extracts the first SQL statement from a text blob.
    1) Looks for a ```sql ... ``` fenced block.
    2) Otherwise, uses sqlparse to parse and returns the first statement.
    """
    # Try fenced SQL block first
    fenced = re.search(r"```sql\s*(.*?)\s*```", full_text, re.DOTALL | re.IGNORECASE)
    if fenced:
        logger.debug("SQL fenced block found.")
        return fenced.group(1).strip()

    # Fallback: parse entire text and grab first statement
    statements = sqlparse.parse(full_text)
    if statements:
        stmt = statements[0]
        sql = str(stmt).strip()
        logger.debug("Extracted SQL via sqlparse: %s", sql)
        return sql

    logger.warning("No SQL statement could be extracted.")
    return ""


def is_valid_sql_select(query: str) -> bool:
    """
    Validates that the provided query is a single safe SELECT statement.
    - Allows optional leading CTEs (WITH ...)
    - Strips comments & whitespace when checking DML
    - Blocks queries containing any DANGEROUS_KEYWORDS
    """
    query = query.strip()
    if not query:
        logger.warning("Empty SQL query.")
        return False

    # Parse and ensure exactly one statement
    parsed = sqlparse.parse(query)
    if len(parsed) != 1:
        logger.warning("Expected a single SQL statement, found %d.", len(parsed))
        return False

    stmt = parsed[0]
    # Filter out whitespace and comments
    tokens = [t for t in stmt.tokens if t.ttype not in (Whitespace, Comment)]
    if not tokens:
        logger.warning("No meaningful tokens in SQL statement.")
        return False

    # Allow leading WITH (CTE) before SELECT
    idx = 0
    first = tokens[0]
    if first.ttype in Keyword and first.value.upper() == 'WITH':
        # find the SELECT after the CTE
        for i, t in enumerate(tokens):
            if t.ttype is DML and t.value.upper() == 'SELECT':
                idx = i
                break
        else:
            logger.warning("CTE found but no SELECT inside it.")
            return False

    # Check that the core DML is SELECT
    core = tokens[idx]
    if core.ttype is not DML or core.value.upper() != 'SELECT':
        logger.warning("Query is not a SELECT statement: %s", core.value)
        return False

    # Scan for dangerous keywords anywhere in the flattened tokens
    for t in stmt.flatten():
        if t.ttype in Keyword and t.value.upper() in DANGEROUS_KEYWORDS:
            logger.error("Dangerous keyword detected: %s", t.value.upper())
            return False

    return True