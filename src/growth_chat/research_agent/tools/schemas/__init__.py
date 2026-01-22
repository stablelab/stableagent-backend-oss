"""Schemas for Research Agent tools.

Re-exports all schema types for convenient importing.
"""

# Common schemas
from .common_schemas import (
    DAOInfo,
    DAOListInput,
    DiscordMessageResult,
    DiscordSearchInput,
    DiscoursePostResult,
    DiscourseSearchInput,
    GitHubCommitResult,
    GitHubRepoResult,
    GitHubSearchInput,
    ProposalResult,
    ProposalSearchInput,
    TelegramMessageResult,
    TelegramSearchInput,
    VoteResult,
    VotesSearchInput,
)

# Discourse schemas
from .discourse_schemas import (
    DiscourseSearchInput as DiscourseToolInput,
    DiscoursePostOutput,
    DiscourseSearchOutput,
)

# Snapshot schemas
from .snapshot_schemas import (
    SnapshotSearchInput,
    SnapshotProposalOutput,
    SnapshotSearchOutput,
)

# Tally schemas
from .tally_schemas import (
    TallySearchInput,
    TallyProposalOutput,
    TallySearchOutput,
)

# GitHub schemas
from .github_schemas import (
    GitHubSearchInput as GitHubToolInput,
    GitHubRepoOutput,
    GitHubSearchOutput,
)

# Telegram schemas
from .telegram_schemas import (
    TelegramSearchInput as TelegramToolInput,
    TelegramMessageOutput,
    TelegramSearchOutput,
)

# Discord schemas
from .discord_schemas import (
    DiscordSearchInput as DiscordToolInput,
    DiscordMessageOutput,
    DiscordSearchOutput,
)

# Votes schemas
from .votes_schemas import (
    VotesSearchInput as VotesToolInput,
    VoteRecordOutput,
    VoteAggregation,
    VotesSearchOutput,
)

__all__ = [
    # Common schemas
    "DAOInfo",
    "DAOListInput",
    "DiscordMessageResult",
    "DiscordSearchInput",
    "DiscoursePostResult",
    "DiscourseSearchInput",
    "GitHubCommitResult",
    "GitHubRepoResult",
    "GitHubSearchInput",
    "ProposalResult",
    "ProposalSearchInput",
    "TelegramMessageResult",
    "TelegramSearchInput",
    "VoteResult",
    "VotesSearchInput",
    # Discourse
    "DiscourseToolInput",
    "DiscoursePostOutput",
    "DiscourseSearchOutput",
    # Snapshot
    "SnapshotSearchInput",
    "SnapshotProposalOutput",
    "SnapshotSearchOutput",
    # Tally
    "TallySearchInput",
    "TallyProposalOutput",
    "TallySearchOutput",
    # GitHub
    "GitHubToolInput",
    "GitHubRepoOutput",
    "GitHubSearchOutput",
    # Telegram
    "TelegramToolInput",
    "TelegramMessageOutput",
    "TelegramSearchOutput",
    # Discord
    "DiscordToolInput",
    "DiscordMessageOutput",
    "DiscordSearchOutput",
    # Votes
    "VotesToolInput",
    "VoteRecordOutput",
    "VoteAggregation",
    "VotesSearchOutput",
]
