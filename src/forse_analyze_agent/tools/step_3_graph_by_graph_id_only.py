import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.forse_analyze_agent.utils.validators import get_required_env
from src.utils.logger import logger

from .cgl_types import DashboardGraph, DashboardGraphs


class GraphIdInput(BaseModel):
    graph_id: str = Field(..., description="The ID of the graph to fetch metadata for")
    dashboard_id: str = Field(
        ..., description="The ID of the dashboard to fetch graphs for"
    )


@tool(
    name_or_callable="step_3_graph_by_graph_id_only",
    description="Fetch graph metadata by graph ID",
    args_schema=GraphIdInput,
)
async def step_3_graph_by_graph_id_only(
    dashboard_id: str, graph_id: str, timeout: int = 30
) -> DashboardGraph:
    """Fetch graphs metadata by dashboard ID."""
    base_url = get_required_env("FORSE_BACKEND_URL")

    url = f"{base_url}/api/graphs/newdashboard/{dashboard_id}/graphs"
    cookies = {"jwt": get_required_env("FORSE_BACKEND_JWT")}

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.debug(f"Fetching: {url}")
            response = await client.get(url, cookies=cookies)
            response.raise_for_status()
            response_json: DashboardGraphs = response.json()
            response_json_graphs: list[DashboardGraph] = response_json.get("graphs", [])
            matching_graphs = [
                g for g in response_json_graphs if g.get("graph_id") == graph_id
            ]
            if not matching_graphs:
                raise ValueError(f"Graph with id {graph_id} not found")
            return matching_graphs[0]

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching graphs: {e.response.status_code}")
            # can't raise error here otherwise chat will load forever
            return []
        except Exception as e:
            logger.error(f"Error fetching graphs: {str(e)}")
            return []
