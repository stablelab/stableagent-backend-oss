from typing import Type, List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool

import os
import json
import time
import requests

from src.services.database import DatabaseService
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event


class CoinGeckoPriceInput(BaseModel):
    action: str = Field(
        ...,
        description=(
            "Operation to perform: 'current' (simple price by id), 'series' (historical market_chart or range), "
            "'token_current' (by contract on a given chain platform), or 'search' (search assets by query)."
        ),
    )
    ids: List[str] = Field(default_factory=list, description="List of CoinGecko asset IDs (e.g., 'uniswap', 'ethereum').")
    vs_currencies: List[str] = Field(default_factory=lambda: ["usd"], description="List of quote currencies (e.g., ['usd','eth']).")
    # Historical series params
    days: Optional[str] = Field(None, description="Span for /market_chart: number of days or presets like 'max'.")
    from_ts: Optional[int] = Field(None, description="Unix seconds for start of /market_chart/range.")
    to_ts: Optional[int] = Field(None, description="Unix seconds for end of /market_chart/range.")
    interval: Optional[str] = Field(None, description="Interval hint for market_chart: e.g., 'daily'.")
    include_fields: List[str] = Field(
        default_factory=lambda: ["prices"],
        description="Which series to return from market_chart: any of ['prices','market_caps','total_volumes'].",
    )
    # Token price by contract
    chain_platform: Optional[str] = Field(
        None,
        description=(
            "CoinGecko platform string for /simple/token_price/{platform} (e.g., 'ethereum', 'arbitrum-one', 'base')."
        ),
    )
    contracts: List[str] = Field(default_factory=list, description="Contract addresses for token_current action.")
    # DB mapping helpers
    dao_ids: List[str] = Field(
        default_factory=list,
        description="If provided, attempt to map Snapshot space IDs to CoinGecko IDs via internal.daos or snapshot.daolist.",
    )
    limit: int = Field(20, description="Max rows to return per action to avoid huge payloads.")
    search_query: Optional[str] = Field(None, description="Search query for action='search'.")


class CoinGeckoPriceTool(BaseTool):
    name: str = "coingecko_price_tool"
    description: str = (
        "Fetch price data from CoinGecko Pro: current prices, historical series, token prices by contract, and search. "
        "Supports mapping DAO snapshot IDs to CoinGecko IDs via the database for integration. "
        "Set environment variable COINGECKO_API_KEY for Pro."
    )
    args_schema: Type[BaseModel] = CoinGeckoPriceInput

    # ---- HTTP helpers
    def _get_base_url(self) -> str:
        key = os.environ.get("COINGECKO_API_KEY", "").strip()
        if key:
            return os.environ.get("COINGECKO_API_BASE", "https://pro-api.coingecko.com/api/v3").rstrip("/")
        return os.environ.get("COINGECKO_API_BASE", "https://api.coingecko.com/api/v3").rstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        key = os.environ.get("COINGECKO_API_KEY", "").strip()
        if key:
            headers["x-cg-pro-api-key"] = key
        return headers

    def _http_get(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any] | List[Any]]:
        try:
            url = f"{self._get_base_url()}{path}"
            r = requests.get(url, headers=self._headers(), params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error("CoinGeckoPriceTool: GET %s failed: %s", path, e, exc_info=True)
            return None

    # ---- DB mapping
    def _map_dao_ids_to_coingecko_ids(self, dao_ids: List[str]) -> List[str]:
        if not dao_ids:
            return []
        # Sanitize and build IN list
        safe: List[str] = []
        for d in dao_ids:
            if not isinstance(d, str):
                continue
            s = d.strip()
            if not s:
                continue
            safe.append(s.replace("'", "''"))
        if not safe:
            return []
        in_list = ", ".join([f"'{s}'" for s in safe])
        # Prefer internal.daos.coingecko_token_id when available, fallback to snapshot.daolist.coingecko
        sql = (
            "WITH from_daos AS (\n"
            "  SELECT DISTINCT LOWER(coalesce(coingecko_token_id, '')) AS cg\n"
            "  FROM internal.daos\n"
            f"  WHERE LOWER(snapshot_id) IN ({in_list})\n"
            "), from_snapshot AS (\n"
            "  SELECT DISTINCT LOWER(coalesce(coingecko, '')) AS cg\n"
            "  FROM snapshot.daolist\n"
            f"  WHERE LOWER(dao_id) IN ({in_list})\n"
            ")\n"
            "SELECT cg FROM from_daos WHERE cg <> ''\n"
            "UNION\n"
            "SELECT cg FROM from_snapshot WHERE cg <> ''\n"
            "LIMIT 200"
        )
        try:
            rows = DatabaseService.query_database(None, sql) or []
            out = [str(r.get("cg", "")).strip() for r in rows if isinstance(r, dict)]
            return [x for x in out if x]
        except Exception as e:
            logger.error("CoinGeckoPriceTool: DB mapping error: %s", e, exc_info=True)
            return []

    # ---- Flatteners
    def _flatten_simple_price(self, payload: Dict[str, Any], ids: List[str], vs: List[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for asset_id, data in (payload or {}).items():
            if not isinstance(data, dict):
                continue
            for quote in vs:
                val = data.get(quote)
                if val is None:
                    continue
                rows.append({
                    "id": asset_id,
                    "vs_currency": quote,
                    "price": val,
                })
        # Preserve requested IDs order if possible
        if ids:
            order: Dict[str, int] = {v: i for i, v in enumerate(ids)}
            rows.sort(key=lambda r: order.get(str(r.get("id")), 10**9))
        return rows[: max(1, min(200, len(rows)))]

    def _flatten_token_simple_price(self, payload: Dict[str, Any], platform: str, vs: List[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for addr, data in (payload or {}).items():
            if not isinstance(data, dict):
                continue
            for quote in vs:
                val = data.get(quote)
                if val is None:
                    continue
                rows.append({
                    "platform": platform,
                    "contract_address": addr,
                    "vs_currency": quote,
                    "price": val,
                })
        return rows

    def _flatten_market_chart(self, asset_id: str, vs: str, payload: Dict[str, Any], include_fields: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        field_map = {
            "prices": "price",
            "market_caps": "market_cap",
            "total_volumes": "total_volume",
        }
        include = [f for f in include_fields if f in field_map]
        for field in include:
            series = payload.get(field) if isinstance(payload, dict) else None
            if not isinstance(series, list):
                continue
            metric = field_map[field]
            for pair in series:
                if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
                    continue
                ts_ms, val = pair[0], pair[1]
                out.append({
                    "id": asset_id,
                    "vs_currency": vs,
                    "timestamp": int(ts_ms // 1000),
                    metric: val,
                })
        return out

    # ---- Action handlers
    def _handle_current(self, ids: List[str], vs: List[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        params = {
            "ids": ",".join(ids[:200]),
            "vs_currencies": ",".join(vs[:20]),
        }
        payload = self._http_get("/simple/price", params)
        if not isinstance(payload, dict):
            return []
        return self._flatten_simple_price(payload, ids, vs)

    def _handle_token_current(self, platform: str, contracts: List[str], vs: List[str]) -> List[Dict[str, Any]]:
        if not platform or not contracts:
            return []
        params = {
            "contract_addresses": ",".join(contracts[:100]),
            "vs_currencies": ",".join(vs[:20]),
        }
        path = f"/simple/token_price/{platform}"
        payload = self._http_get(path, params)
        if not isinstance(payload, dict):
            return []
        return self._flatten_token_simple_price(payload, platform, vs)

    def _handle_series(self, ids: List[str], vs: List[str], days: Optional[str], from_ts: Optional[int], to_ts: Optional[int], interval: Optional[str], include_fields: List[str], hard_limit: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not ids or not vs:
            return rows
        # market_chart supports only one id per call; we loop but cap
        max_ids = min(len(ids), 8)  # avoid huge loops
        for asset_id in ids[:max_ids]:
            for quote in vs[:3]:
                if from_ts is not None and to_ts is not None:
                    params = {"vs_currency": quote, "from": int(from_ts), "to": int(to_ts)}
                    path = f"/coins/{asset_id}/market_chart/range"
                else:
                    dval = days or "30"
                    params = {"vs_currency": quote, "days": dval}
                    if interval:
                        params["interval"] = interval
                    path = f"/coins/{asset_id}/market_chart"
                payload = self._http_get(path, params)
                if isinstance(payload, dict):
                    flattened = self._flatten_market_chart(asset_id, quote, payload, include_fields)
                    rows.extend(flattened)
                # Cap result size to keep the tool compact
                if len(rows) > hard_limit:
                    return rows[:hard_limit]
        return rows

    def _handle_search(self, query: str, hard_limit: int) -> List[Dict[str, Any]]:
        if not query:
            return []
        payload = self._http_get("/search", {"query": query})
        if not isinstance(payload, dict):
            return []
        coins = payload.get("coins") if isinstance(payload, dict) else None
        out: List[Dict[str, Any]] = []
        if isinstance(coins, list):
            for c in coins[: hard_limit]:
                if not isinstance(c, dict):
                    continue
                out.append({
                    "id": c.get("id"),
                    "symbol": c.get("symbol"),
                    "name": c.get("name"),
                    "market_cap_rank": c.get("market_cap_rank"),
                    "thumb": c.get("thumb"),
                })
        return out

    # ---- Entry point
    def _run(
        self,
        action: str,
        ids: List[str] = [],
        vs_currencies: List[str] = ["usd"],
        days: Optional[str] = None,
        from_ts: Optional[int] = None,
        to_ts: Optional[int] = None,
        interval: Optional[str] = None,
        include_fields: List[str] = ["prices"],
        chain_platform: Optional[str] = None,
        contracts: List[str] = [],
        dao_ids: List[str] = [],
        limit: int = 20,
        search_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            logger.info("CoinGeckoPriceTool: action=%s ids=%d contracts=%d dao_ids=%d", action, len(ids or []), len(contracts or []), len(dao_ids or []))
            try:
                emit_tool_event("coingecko.input", {
                    "action": action,
                    "ids": ids[:5],
                    "vs_currencies": vs_currencies[:5],
                    "contracts": contracts[:5],
                    "dao_ids": dao_ids[:5],
                })
            except Exception:
                pass
            hard_limit = max(1, min(int(limit or 20), 10000))
            # DB mapping if requested
            if dao_ids:
                mapped = self._map_dao_ids_to_coingecko_ids(dao_ids)
                # Merge mapped IDs with provided ids (de-duplicate)
                if mapped:
                    merged = list(dict.fromkeys((ids or []) + mapped))
                    ids = merged

            act = (action or "").strip().lower()
            if act == "current":
                rows = self._handle_current(ids, vs_currencies)[:hard_limit]
                try:
                    emit_tool_event("coingecko.output", {"count": len(rows or []), "sample": rows[:3]})
                except Exception:
                    pass
                return rows
            if act == "token_current":
                rows = self._handle_token_current(chain_platform or "", contracts, vs_currencies)[:hard_limit]
                try:
                    emit_tool_event("coingecko.output", {"count": len(rows or []), "sample": rows[:3]})
                except Exception:
                    pass
                return rows
            if act == "series":
                rows = self._handle_series(ids, vs_currencies, days, from_ts, to_ts, interval, include_fields, hard_limit)
                try:
                    emit_tool_event("coingecko.output", {"count": len(rows or []), "sample": rows[:3]})
                except Exception:
                    pass
                return rows
            if act == "search":
                rows = self._handle_search(search_query or (ids[0] if ids else ""), hard_limit)
                try:
                    emit_tool_event("coingecko.output", {"count": len(rows or []), "sample": rows[:3]})
                except Exception:
                    pass
                return rows

            logger.warning("CoinGeckoPriceTool: unsupported action '%s'", action)
            return []
        except Exception as e:
            logger.error("CoinGeckoPriceTool: unexpected error: %s", e, exc_info=True)
            return []

    async def _arun(self, **kwargs) -> List[Dict[str, Any]]:
        return self._run(**kwargs)


