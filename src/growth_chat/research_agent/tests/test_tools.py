"""Unit tests for Research Agent tools.

Tests tool input validation, output formatting, and basic functionality.
"""
import pytest
from unittest.mock import MagicMock, patch

from ..tools.schemas.common_schemas import (
    DiscourseSearchInput,
    ProposalSearchInput,
    TelegramSearchInput,
    DiscordSearchInput,
    VotesSearchInput,
    GitHubSearchInput,
    DAOListInput,
)


class TestSchemaValidation:
    """Test input schema validation."""
    
    def test_discourse_search_input_valid(self):
        """Test valid discourse search input."""
        input_data = DiscourseSearchInput(query="governance proposal")
        assert input_data.query == "governance proposal"
        assert input_data.limit == 10  # default
        assert input_data.dao_id is None
    
    def test_discourse_search_input_with_dao(self):
        """Test discourse search with DAO filter."""
        input_data = DiscourseSearchInput(
            query="treasury",
            dao_id="aave",
            limit=20
        )
        assert input_data.dao_id == "aave"
        assert input_data.limit == 20
    
    def test_proposal_search_input_valid(self):
        """Test valid proposal search input."""
        input_data = ProposalSearchInput(query="incentives")
        assert input_data.query == "incentives"
        assert input_data.limit == 10
    
    def test_proposal_search_with_state_filter(self):
        """Test proposal search with state filter."""
        input_data = ProposalSearchInput(
            query="grants",
            state="active",
            dao_id="compound"
        )
        assert input_data.state == "active"
        assert input_data.dao_id == "compound"
    
    def test_telegram_search_input(self):
        """Test telegram search input."""
        input_data = TelegramSearchInput(query="airdrop")
        assert input_data.query == "airdrop"
        assert input_data.limit == 10
    
    def test_discord_search_input(self):
        """Test discord search input."""
        input_data = DiscordSearchInput(query="governance update")
        assert input_data.query == "governance update"
    
    def test_votes_search_input(self):
        """Test votes search input."""
        input_data = VotesSearchInput(proposal_id="QmXyz123")
        assert input_data.proposal_id == "QmXyz123"
        assert input_data.limit == 50  # default
    
    def test_votes_search_by_voter(self):
        """Test votes search by voter address."""
        input_data = VotesSearchInput(voter="0x1234567890abcdef")
        assert input_data.voter == "0x1234567890abcdef"
    
    def test_github_search_input(self):
        """Test GitHub search input."""
        input_data = GitHubSearchInput(query="smart contracts")
        assert input_data.query == "smart contracts"
    
    def test_dao_list_input(self):
        """Test DAO list input."""
        input_data = DAOListInput(name="uni")
        assert input_data.name == "uni"
        assert input_data.limit == 20


class TestDatabaseClient:
    """Test database client functionality."""
    
    @patch('src.growth_chat.research_agent.tools.database_client.get_connection_pool')
    @patch('src.growth_chat.research_agent.tools.database_client.EmbeddingsService')
    def test_generate_embedding(self, mock_embedding_service, mock_pool):
        """Test embedding generation."""
        from ..tools.database_client import ResearchDatabaseClient
        
        # Mock embedding service
        mock_service = MagicMock()
        mock_service.embed_documents.return_value = [[0.1] * 3072]
        mock_embedding_service.return_value = mock_service
        
        client = ResearchDatabaseClient()
        embedding = client.generate_embedding("test query")
        
        assert len(embedding) == 3072
        mock_service.embed_documents.assert_called_once_with(["test query"])
    
    @patch('src.growth_chat.research_agent.tools.database_client.get_connection_pool')
    def test_format_vector(self, mock_pool):
        """Test vector formatting for PostgreSQL."""
        from ..tools.database_client import ResearchDatabaseClient
        
        client = ResearchDatabaseClient()
        embedding = [0.1, 0.2, 0.3]
        vector_literal = client.format_vector(embedding)
        
        assert vector_literal.startswith("'[")
        assert vector_literal.endswith("]'::vector")
        assert "0.1" in vector_literal
    
    @patch('src.growth_chat.research_agent.tools.database_client.get_connection_pool')
    def test_format_empty_vector(self, mock_pool):
        """Test formatting empty vector returns zero vector."""
        from ..tools.database_client import ResearchDatabaseClient
        
        client = ResearchDatabaseClient()
        vector_literal = client.format_vector([])
        
        assert "::vector" in vector_literal


class TestToolFactory:
    """Test tool factory creates all tools."""
    
    def test_create_research_tools(self):
        """Test that tool factory creates expected tools."""
        from ..tools.tools import create_research_tools
        
        tools = create_research_tools()
        
        # Should have multiple tools
        assert len(tools) >= 8
        
        # Check tool names exist
        tool_names = [t.name for t in tools]
        assert "discourse_search" in tool_names
        assert "snapshot_proposals" in tool_names
        assert "tally_proposals" in tool_names
        assert "votes_lookup" in tool_names
        assert "telegram_search" in tool_names
        assert "discord_search" in tool_names
        assert "dao_catalog" in tool_names

