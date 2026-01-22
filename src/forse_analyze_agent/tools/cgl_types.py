from typing import List

from pydantic import BaseModel


class GraphData(BaseModel):
    position: str
    value: str
    label: str
    category: str


class EventData(BaseModel):
    event_id: str
    event_name: str
    value: str
    affiliation: str | None


class CategoryData(BaseModel):
    data: List[GraphData]
    events: List
    filters: List


class GraphCategory(BaseModel):
    graph_id: str
    category_id: str
    category_name: str
    value_label: str
    value_type: str
    position_label: str
    position_type: str
    formatter_type: str
    schema_name: str
    table_name: str
    type: str  # chart type
    active: bool
    version: int
    size_label: str | None
    comment_position: str
    auto_format_labels: bool
    order_idx: int
    sort_labels: bool
    tooltip_axis: bool
    tooltip_labels: str
    tooltip_custom: str
    enable_aggregation: str
    aggregation_method: str


class DashboardGraph(BaseModel):
    graph_id: str
    title: str
    info: str | None
    dashboard_id: str
    type: str
    group_ids: List[int]
    tab_index: int | None
    row_number: int
    col_number: int
    col_span: int
    order_idx: int | None
    active: bool
    row_span: int | None
    variant_id: str | None
    categories: List[GraphCategory]
    comments: List[str]
    filters: List[str]


class DashboardGraphs(BaseModel):
    graphs: List[DashboardGraph]


class DaoSpaceSub(BaseModel):
    title: str
    dashboard_id: str
    icon: str
    description: str
    order_idx: int
    updated_at: str
    legacy: bool
    switch_group: None | str
    switches: List


class DaoSpace(BaseModel):
    space_id: str
    title: str
    icon: str
    description: str
    order_idx: int
    sub: List[DaoSpaceSub]
