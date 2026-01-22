from src.forse_analyze_agent.tools.custom_analysis import analyze_graph_custom
from src.forse_analyze_agent.tools.dashboard_overview import fetch_dashboard_overview
from src.forse_analyze_agent.tools.step_1_fetch_dao_spaces import (
    step_1_fetch_dao_spaces,
)
from src.forse_analyze_agent.tools.step_2_graphs_by_dashboard_id import (
    step_2_graphs_by_dashboard_id,
)
from src.forse_analyze_agent.tools.step_3_graph_by_graph_id_only import (
    step_3_graph_by_graph_id_only,
)
from src.forse_analyze_agent.tools.step_4_graph_data_by_id_and_category_id import (
    step_4_graph_data_by_id_and_category_id,
)

from src.forse_analyze_agent.tools.table_row_count import count_table_rows

AVAILABLE_TOOLS = [
    step_1_fetch_dao_spaces,
    step_2_graphs_by_dashboard_id,
    step_3_graph_by_graph_id_only,
    step_4_graph_data_by_id_and_category_id,
    # count_table_rows, this is for internal usage only
    fetch_dashboard_overview,
    analyze_graph_custom,
]
