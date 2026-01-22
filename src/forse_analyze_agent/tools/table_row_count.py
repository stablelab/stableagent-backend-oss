from langchain_core.tools import tool
from pydantic import BaseModel, Field
from src.services.database import DatabaseService


class TableRowCountInput(BaseModel):
    schema_name: str = Field(
        ..., description="The name of the schema to count the rows in"
    )
    table_name: str = Field(
        ..., description="The name of the table to count the rows in"
    )


@tool(
    name_or_callable="count_table_rows",
    description="Count the number of rows in a table only before executing tool step_4_graph_data_by_id_and_category_id and it stays hidden for internal usage only",
    args_schema=TableRowCountInput,
)
async def count_table_rows(schema_name: str, table_name: str, timeout: int = 30) -> int:
    """Count the number of rows in a table."""
    try:
        _sql = f"SELECT COUNT(*) FROM {schema_name}.{table_name}"
        results = DatabaseService.query_database(None, _sql)
        if results and len(results) > 0 and len(results[0]) > 0:
            return results[0][0]
        return 0
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"Error counting rows in {schema_name}.{table_name}: {e}")
        return -1  # Return -1 to indicate error

