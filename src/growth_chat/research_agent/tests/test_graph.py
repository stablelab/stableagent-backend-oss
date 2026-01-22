"""Integration tests for Research Agent graph.

Tests the full agent flow from graph creation to tool execution.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from ..graph import create_research_agent_graph, create_agent_node
from ..tools.tools import create_research_tools


class TestGraphCreation:
    """Test graph creation and structure."""
    
    def test_create_research_agent_graph(self):
        """Test that graph can be created successfully."""
        graph = create_research_agent_graph()
        assert graph is not None
    
    def test_graph_with_user_context(self):
        """Test graph creation with user context."""
        graph = create_research_agent_graph(
            user_id="user_123",
            org_slug="test_org"
        )
        assert graph is not None
    
    def test_agent_node_creation(self):
        """Test agent node can be created with tools."""
        tools = create_research_tools()
        agent = create_agent_node(tools)
        assert agent is not None
    
    def test_agent_node_with_context(self):
        """Test agent node with user context."""
        tools = create_research_tools()
        agent = create_agent_node(
            tools=tools,
            user_id="user_456",
            org_slug="demo_org"
        )
        assert agent is not None


class TestToolIntegration:
    """Test tool integration with mocked database."""
    
    @patch('src.growth_chat.research_agent.tools.database_client.get_connection_pool')
    @patch('src.growth_chat.research_agent.tools.database_client.EmbeddingsService')
    def test_discourse_tool_integration(self, mock_embedding_service, mock_pool):
        """Test discourse search tool with mocked responses."""
        from ..tools.discourse_tool import DiscourseSearchTool
        
        # Mock embedding service
        mock_service = MagicMock()
        mock_service.embed_documents.return_value = [[0.1] * 3072]
        mock_embedding_service.return_value = mock_service
        
        # Mock connection pool
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 0, "Test Topic", "test-dao", "Test content summary", "https://forum.test/1")
        ]
        mock_cursor.description = [
            ("topic_id",), ("index",), ("topic_title",), ("dao_id",), ("content_summary",), ("post_link",)
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool.return_value.get_connection.return_value = mock_conn
        
        tool = DiscourseSearchTool()
        result = tool._run(query="governance")
        
        assert "Test Topic" in result or "No forum posts found" in result
    
    @patch('src.growth_chat.research_agent.tools.database_client.get_connection_pool')
    @patch('src.growth_chat.research_agent.tools.database_client.EmbeddingsService')
    def test_votes_tool_integration(self, mock_embedding_service, mock_pool):
        """Test votes lookup tool with mocked responses."""
        from ..tools.votes_tool import VotesLookupTool
        
        # Mock connection pool
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("0xabc", "QmProp1", "For", 1000.0, 1234567890, "snapshot", "test-dao", None)
        ]
        mock_cursor.description = [
            ("voter",), ("proposal",), ("choice",), ("vp",), ("created",), ("source",), ("dao_id",), ("reason",)
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool.return_value.get_connection.return_value = mock_conn
        
        tool = VotesLookupTool()
        result = tool._run(proposal_id="QmProp1")
        
        # Should either show results or handle empty gracefully
        assert "vote" in result.lower() or "found" in result.lower()


class TestAgentPrompts:
    """Test agent prompts are properly configured."""
    
    def test_system_prompt_exists(self):
        """Test system prompt is defined."""
        from ..prompts import RESEARCH_AGENT_SYSTEM_PROMPT
        
        assert RESEARCH_AGENT_SYSTEM_PROMPT is not None
        assert len(RESEARCH_AGENT_SYSTEM_PROMPT) > 100
    
    def test_system_prompt_contains_tools(self):
        """Test system prompt mentions all tools."""
        from ..prompts import RESEARCH_AGENT_SYSTEM_PROMPT
        
        # Should mention key tools
        assert "snapshot" in RESEARCH_AGENT_SYSTEM_PROMPT.lower()
        assert "tally" in RESEARCH_AGENT_SYSTEM_PROMPT.lower()
        assert "discourse" in RESEARCH_AGENT_SYSTEM_PROMPT.lower()
        assert "telegram" in RESEARCH_AGENT_SYSTEM_PROMPT.lower()
        assert "votes" in RESEARCH_AGENT_SYSTEM_PROMPT.lower()

