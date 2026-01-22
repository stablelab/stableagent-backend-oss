from typing import Type
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.llm.factory import create_tool_chat_model, identify_model_name, identify_provider
from src.prompts.system_prompts import CONTEXT_PROVIDER_SYSTEM
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event
import time

optional_context = """
ABI=low-level binary interface; API=program interface; Arbitrage=profit from price gaps; Arbitrum=L2 rollups; Archival Node=full node w/ full history; Base Fee=EIP-1559 fee adjuster; Block Gas Estimator=gas predictor; Blockchain=distributed ledger; Bridge=cross-chain transfer; Bulletproofs=short ZK-proofs; Cancel Tx=replacement tx; Censorship=exclude tx; Confirmed Tx=on-chain; Cross-Chain Arbitrage=MEV across chains; Dapp=decentralized app; DeFi=decentralized finance; DEX=decentralized exchange; Dropped Tx=not mined; EIP-1559=fee reform; EOA Tx=user tx; Ethereum=smart contract chain; Ethereum 2.0=consensus layer (PoS); EVM=Ethereum runtime; Failed Tx=unsuccessful tx; Full Node=validates blockchain; Front-running=preempt tx for profit; Gas=tx compute cost; Gas Estimator=fee predictor; Gas Fees=ETH fees; Gas Limit=max gas per tx; Gas Price=ETH per gas unit; Goerli=testnet; Gwei=1e-9 ETH; Internal Tx=contract↔contract; JIT Arbitrage=MEV sandwich around swaps; Kovan=deprecated testnet; L1=base chain; L2=scaling chains; Light Node=partial blockchain client; Liquidations=collateral shortfall sales; Liquidity=asset tradability; Loopring=L2 zk-rollup DEX; Max Fee Per Gas=max gas cost; Max Priority Fee=tip; Mempool=pending tx pool; Mempool Explorer=live tx viewer; Merkle Root=tree hash; Merkle Tree=hash tree; MEV=miner/maximal extractable value; NFT Sniping=MEV targeting NFTs; NFT=unique token; Nonce=tx counter; Notify=tx alert library; Off-Chain=outside chain; On-Chain=recorded on chain; Onboard=wallet connect lib; Optimism=L2 optimistic rollup; Optimistic Rollups=L2 w/ fraud proofs; Pending Pool=ready tx; Pending Simulation=tx pre-check; Pending Tx=unconfirmed tx; Pre-Chain/Pre-Consensus=in-flight tx; PoS=stake-based consensus; PoW=compute consensus; Pool Imbalance Sandwich=MEV pool manipulation; Queued Pool=waiting tx; Rebase Arbitrage=MEV on oracle/rebase; Replacement Tx=cancel/speedup; Rinkeby/Ropsten=deprecated testnets; Sandwiching=MEV price exploit; SDK=dev kit; Searcher=MEV actor; Sidechain=separate but connected chain; Simulation Platform=tx outcome predictor; Smart Contract=on-chain code; Speed Up Tx=faster replacement; State Channel=off-chain tx channel; Stuck Tx=blocked by nonce; Testnet=sandbox chain; Tip=miner incentive; Tokenomics=token economics; TVL=locked asset value; Tx Event Stream=live tx feed; Tx Settlement=final inclusion; Tx Simulation=tx preview; Tx Status=confirmed/failed/dropped/stuck; Type 0 Tx=legacy; Type 2 Tx=EIP-1559; UX=user experience; Wallet=key manager; Web3=decentralized internet; wETH/wrapped tokens=ERC-20 ETH or other chain-wrapped assets; Wei=1e-18 ETH; xDai=PoS sidechain; ZK-Proof=privacy proof; ZK-Rollup=L2 batching w/ proofs; zk-SNARK=succinct ZK-proof; zkSync=L2 zk-rollup.
"""


class ContextExpandInput(BaseModel):
    user_query: str = Field(..., description="The user's question")


class ContextExpanderTool(BaseTool):
    name: str = "context_expander_tool"
    description: str = (
        "Expand a user query into keywords, synonyms, and related terms that will guide retrieval."+ '\n\n' + optional_context
    )
    args_schema: Type[BaseModel] = ContextExpandInput

    def __init__(self, **data):
        super().__init__(**data)
        system_text = "\n".join(CONTEXT_PROVIDER_SYSTEM)
        safe_system_text = system_text.replace("{", "{{").replace("}", "}}")
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", safe_system_text),
            ("human", "User query: {q}\n\nReturn expansions as a single plain text string."),
        ])
        self._llm = create_tool_chat_model(self.name)
        self._chain = self._prompt | self._llm | StrOutputParser()
        try:
            from src.utils.logger import logger  # local import to avoid cycles
            logger.info(
                "ContextExpanderTool: initialized with provider=%s model=%s",
                identify_provider(self._llm),
                identify_model_name(self._llm),
            )
        except Exception:
            pass

    def _run(self, user_query: str) -> str:
        try:
            logger.info("ContextExpanderTool: start user_query_len=%d", len(user_query or ""))
            start_ts = time.time()
            try:
                emit_tool_event("context_expand.input", {"user_query": user_query})
                emit_tool_event("tool.start", {"tool": self.name, "input": {"user_query_len": len(user_query or "")}})
            except Exception:
                pass
            out = self._chain.invoke({"q": user_query})
            logger.info("ContextExpanderTool: done")
            try:
                emit_tool_event("context_expand.output", {"expansion": out})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"length": len(out or "")}})
            except Exception:
                pass
            return out
        except Exception as e:
            logger.error("ContextExpanderTool: error %s", e, exc_info=True)
            try:
                emit_tool_event("context_expand.error", {"message": str(e)})
                emit_tool_event("tool.end", {"tool": getattr(self, 'name', 'context_expander_tool'), "status": "error", "error": str(e)})
            except Exception:
                pass
            return ""

    async def _arun(self, user_query: str) -> str:
        return self._run(user_query)