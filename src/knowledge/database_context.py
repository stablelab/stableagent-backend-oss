DATABASE_SUMMARY = """
This database contains comprehensive DAO governance data across multiple platforms:

• Proposals: Unified cross-platform governance proposals from Snapshot, Tally, Aragon, and MakerDAO with voting metrics, timestamps, and content
• Votes: Individual vote records with voter addresses, voting power, choices, and timestamps  
• Embeddings: Vector embeddings of proposal content for semantic search capabilities
• DAOs: Metadata and configuration for decentralized autonomous organizations
• Discord Messages: Daily aggregated messages from Discord
• Telegram Messages: Messages aggregated over 15-day windows with 5-day overlap, grouped by DAO and topic, including a conceptual summary of key discussion points.• GitHub Commits: Daily aggregated commits from GitHub
• GitHub Commits: Daily commits from GitHub, including authorship, commit metadata, and signature verification.
• GitHub Board: Daily aggregated board progress from GitHub
• Forum Posts: Discussion threads and comments from Discourse forums
• Chain Data: EVM network information and ENS address mappings
• References: Links between proposals and external forum topics

Primary tables: internal.unified_proposals, internal.unified_votelist, internal.unified_embeddings, internal.unified_discord, internal.unified_telegram, internal.unified_discourse_embeddings
Use cases: Governance analytics, vote tracking, semantic proposal search, delegate analysis
"""

DATABASE_CONTEXT = """
  - name: internal.proposal_references
    description: "Links proposals to external references (e.g., forum topics)."
    columns:
      - id: integer
      - snapshot_proposal_id: character varying
      - discourse_topic_id: integer
      - forum_id: text
      - mapping_methods_bitmask: integer
      - tally_id: text

  - name: internal.unified_proposals
    description:
      Materialized view that merges proposals from Snapshot, Tally, Aragon, and MakerDAO.
      Each row contains a minimal, common set of governance fields.
      Use this for cross-platform listing/filtering; join to internal.unified_embeddings for vector search.
    columns:
      - name: proposal_id
        type: text
        description: "Platform-native identifier (Snapshot IPFS/EVM hash, Tally/Aragon/Maker numeric/string cast to text)."
        example: "0x0020f6…cf542"
      - name: source
        type: text
        description: "Origin platform: 'snapshot' | 'tally' | 'aragon' | 'onchain_daos'."
        example: "snapshot"
      - name: dao_id
        type: text
        description: "Platform-specific DAO identifier (Snapshot space, Tally slug, Aragon ENS/address, MAkerDao MakerDAO, onchain DAO contract_address etc.)"
        example: "uniswapgovernance.eth"
      - name: title
        type: text
        description: "Proposal title."
        example: "DeFi Education Fund Temp Check - Options"
      - name: body
        type: text
        description: "Proposal body/description (Markdown or HTML)."
        example: "This is a parallel proposal …"
      - name: created_at
        type: "timestamp with time zone"
        description: "Creation time (Snapshot: to_timestamp(created); Tally: start_timestamp; Aragon/Maker: start_date)."
        example: "2024-04-30 13:02:20+00"
      - name: vote_start
        type: "bigint"
        description: "Unix epoch seconds when voting opens."
        example: 1714465740
      - name: vote_end
        type: "bigint"
        description: "Unix epoch seconds when voting closes."
        example: 1714897800
      - name: state
        type: text
        description: "Lifecycle state (e.g., active, closed, executed)."
        example: "active"
      - name: for_votes
        type: numeric
        description: "Total 'for' votes/power (Snapshot: scores_total; Tally/Aragon/Maker: source fields)."
        example: 2501028
      - name: against_votes
        type: numeric
        description: "Total 'against' votes/power; may be NULL for sources that don't report it."
        example: 1000000
      - name: abstain_votes
        type: numeric
        description: "Total 'abstain' votes/power; may be NULL."
        example: 500000
      - name: votes_object
        type: numeric
        description: "Extra aggregated vote metric where available (e.g., MakerDAO total_mkr_participation); NULL otherwise."
        example: null
      - name: quorum
        type: numeric
        description: "Minimum voting power required for the proposal to pass."
        example: 10000000
      - name: link
        type: text
        description: "Canonical UI link to view the proposal (may be NULL)."
        example: "https://snapshot.org/#/…"
    indexes:
      - "unique (proposal_id, source)"
      - "btree (dao_id)"
      - "btree (state)"
      - "btree (created_at)"
      - "btree (proposal_id)"
      - "btree (title)"

  - name: internal.unified_embeddings
    description:
      Materialized view unifying embedding vectors from Snapshot, Tally, Aragon, and MakerDAO.
      Use this for pgvector similarity, then JOIN back to internal.unified_proposals
      on (proposal_id, source) to fetch titles/metadata.
    columns:
      - name: proposal_id
        type: text
        description: "FK to internal.unified_proposals.proposal_id (pair with source)."
        example: "0x0020f6…cf542"
      - name: source
        type: text
        description: "Origin platform: 'snapshot' | 'tally' | 'aragon' | 'onchain_daos'."
        example: "snapshot"
      - name: dao_id
        type: text
        description: "Platform-specific DAO identifier (copied from source tables)."
        example: "uniswapgovernance.eth"
      - name: index
        type: integer
        description: "Chunk index (0-based). Alias in queries if desired: index AS emb_index."
        example: 0
      - name: embedding
        type: "vector(768)"
        description: "768-d vector. Indexed with ivfflat (vector_cosine_ops; lists=100)."
        example: "[0.012, -0.034, …]"
    indexes:
      - "unique (proposal_id, source, index)"
      - "ivfflat (embedding vector_cosine_ops) with (lists = 100)"

  - name: internal.unified_discord
    description:
      Materialized view combining Discord messages with optional embeddings. Aggregates messages by DAO and date,
      includes both raw content and summarization embeddings for downstream analysis and semantic search.
    columns:
      - name: date
        type: date
        description: "Date on which the Discord messages were sent (UTC)."
        example: "2025-08-19"
      - name: dao_id
        type: text
        description: "Identifier for the DAO, using either snapshot_id or name from internal.daos."
        example: "optimism.eth"
      - name: start_unix
        type: bigint
        description: "Unix timestamp (in seconds) of the earliest message in this group."
        example: 1755572641
      - name: end_unix
        type: bigint
        description: "Unix timestamp (in seconds) of the latest message in this group."
        example: 1755576741
      - name: content
        type: jsonb
        description:
          Aggregated list of messages for the given DAO and date, including metadata such as author, channel,
          message content, and referenced message details.
        example:
          - unix_ts: 1755572641
            Channel: "🔗│validators"
            Author: "relik310 (r3lik)"
            Message: "We're syncing from scratch. Any ideas?"
            referenced_message_content: "hi how long is the epoch sync supposed to take from scratch?"
            referenced_author: "relik310"
      - name: content_summary
        type: jsonb
        description: "Optional summarized representation of the content field, generated via LLM or heuristic processing."
        example:
          summary: "Participants discuss syncing nodes from scratch and errors seen during the process."
      - name: embedding
        type: vector(768)
        description: "Embedding vector representation (768-dim) of the summarized content for semantic search or clustering."
        example: "[0.0123, -0.0451, ..., 0.0087]"
    indexes:
      - "unique (date, dao_id, start_unix, end_unix)"
      - "btree (dao_id)"
      - "btree (date)"
      - "btree (start_unix)"
      - "btree (end_unix)"

  - name: internal.unified_discourse_embeddings
    description:
      Materialized view aggregating content embeddings from Discourse forum posts.
      Each row represents a vector embedding of a post segment (indexed by `index`) within a given topic,
      enriched with DAO identification and topic metadata. Enables semantic search and topic-level analysis
      of DAO discussions on Discourse.
    columns:
      - name: topic_id
        type: integer
        description: "Topic ID that the post and embedding belong to. Shared across all posts in a discussion thread."
        example: 519
      - name: index
        type: integer
        description: "Chunk index for the embedding content (used when a post or topic is split into multiple pieces for embedding)."
        example: 0
      - name: topic_title
        type: text
        description: "Title of the topic or discussion thread on the Discourse forum."
        example: "[Proposal] Balancer Academy - Marketing Via New User Education"
      - name: dao_id
        type: text
        description:
          Identifier of the DAO, derived from internal.daos (either the snapshot_id or name). Used to group discussions by DAO.
        example: "balancer.eth"
      - name: content_summary
        type: jsonb
        description:
          Summarized content or cleaned version of the discourse post (used for generating embeddings).
          Typically plain-text, semantically meaningful, and stripped of markup or boilerplate.
        example:
          summary: "This proposal suggests using Balancer Academy to educate new users and drive adoption."
      - name: embedding
        type: vector(768)
        description:
          768-dimensional vector embedding representing the semantic meaning of the content_summary.
          Useful for similarity search, clustering, and topic modeling.
        example: "[0.0112, -0.0849, 0.1023, ..., 0.0089]"
    indexes:
      - "unique (topic_id, dao_id, index)"
      - "btree (dao_id, index)"
      - "btree (topic_title)"
      - "btree (topic_title, index)"

  - name: telegram.conceptual_telegram
    description:
      Base table containing individual conceptualized Telegram messages collected from DAO-related
      discussion channels. Each row represents a single Telegram message mapped to a DAO, 
      time window, and optionally a discussion topic.  
      Serves as the foundational layer for analytical and semantic models such as 
      `internal.unified_telegram` and `telegram.telegram_conceptual_embeddings`.
    columns:
      - name: message_id
        type: numeric
        description:
          Unique identifier for the Telegram message within a specific DAO–window combination.
          Corresponds to the original message ID from the Telegram API.
        example: 305842
      - name: dao_id
        type: integer
        description:
          Identifier linking the message to a specific DAO entity.
          Used for partitioning and aggregation across DAOs.
        example: 42
      - name: window_number
        type: integer
        description:
          Sequential index representing the analysis time window during which the message occurred.
          Used for temporal segmentation of discussions.
        example: 8
      - name: user_id
        type: numeric
        description:
          Unique identifier of the user who sent the message.
          Maps to Telegram’s internal user ID.
        example: 918374920
      - name: username
        type: text
        description:
          Username or handle of the message sender.
          May be null for anonymous or system messages.
        example: "cryptobuilder42"
      - name: channel_id
        type: numeric
        description:
          Identifier for the Telegram channel or group in which the message was posted.
          Enables tracking of multiple DAO-related Telegram spaces.
        example: 132948572
      - name: unix_ts
        type: numeric
        description:
          UNIX timestamp (in seconds) when the message was originally sent.
          Used for chronological ordering and time-based aggregations.
        example: 1610563489
      - name: edit_date
        type: numeric
        description:
          UNIX timestamp (in seconds) of the last message edit, if applicable.
          Null if the message was never edited.
        example: 1610564092
      - name: message
        type: text
        description:
          Full text content of the Telegram message.
          Can include URLs, mentions, and emojis.
        example:
          "stETH you can get if you stake your ETH tokens using Lido. Visit https://stake.lido.fi"
      - name: topic_id
        type: integer
        description:
          Numeric identifier representing the topic or cluster the message belongs to.
          Assigned during topic modeling or clustering. May be null for unclassified messages.
        example: 3
      - name: topic_title
        type: text
        description:
          Human-readable title describing the topic to which the message is assigned.
          Derived from topic modeling or embedding summarization.
        example: "Lido staking liquidity and governance"
      - name: topic_representation
        type: text[]
        description:
          Array of representative keywords or tokens summarizing the topic’s semantic core.
          Generated via topic modeling or embedding extraction.
        example: "{steth, liquidity, lido, staking, governance}"
      - name: window_start
        type: timestamptz
        description:
          Start timestamp (UTC) for the analysis window that includes this message.
          Typically corresponds to the first message boundary in a 15-day period.
        example: "2021-01-01 00:00:00+00"
      - name: window_end
        type: timestamptz
        description:
          End timestamp (UTC) for the analysis window that includes this message.
          Typically extends 15 days from `window_start` with a 5-day overlap.
        example: "2021-01-15 00:00:00+00"

  - name: internal.unified_telegram
    description:
      Materialized view that aggregates conceptual Telegram messages per DAO, window, and topic.
      Combines text messages from `telegram.conceptual_telegram` with semantic embeddings
      and topic metadata from `telegram.telegram_conceptual_embeddings`.
      Includes all messages (with timestamps) concatenated per DAO–window–topic group.
      Automatically refreshed every 2 hours via pg_cron.
    columns:
      - name: dao_id
        type: text
        description: "Unique identifier for the DAO (e.g., 'lido.eth', 'arbitrum.eth')."
        example: "lido.eth"
      - name: window_number
        type: integer
        description:
          Sequential number representing the analysis time window for the DAO.
          Each window spans **15 days** of Telegram discussions and includes a **5-day overlap**
          from the previous window to maintain temporal continuity in topic tracking.
        example: 8
      - name: topic_id
        type: integer
        description: "Unique identifier of the topic within the DAO and time window."
        example: -1
      - name: topic_title
        type: text
        description: "Human-readable title describing the discussion topic."
        example: "Lido DAO: stETH Liquidity and Governance Challenges"
      - name: topic_representation
        type: text[]
        description: "Array of representative keywords summarizing the topic content."
        example: "{pool,curve,deposit,withdraw,steth,liquidity}"
      - name: window_start
        type: timestamptz
        description: "Start timestamp (UTC) of the 15-day analysis window."
        example: "2020-12-27 00:00:00+00"
      - name: window_end
        type: timestamptz
        description: "End timestamp (UTC) of the 15-day window (with 5-day overlap)."
        example: "2021-01-15 00:00:00+00"
      - name: start_unix
        type: bigint
        description: "Earliest UNIX timestamp of messages within the window."
        example: 1609048898
      - name: end_unix
        type: bigint
        description: "Latest UNIX timestamp of messages within the window."
        example: 1610666991
      - name: content
        type: text
        description:
          Narrative summary or synthesized content describing the aggregated discussion
          within the DAO–window–topic group.
          Derived from `telegram.telegram_conceptual_embeddings.content`.
        example:
          "The discussion on Lido DAO's stETH liquidity and governance challenges spanned from
          December 27, 2020, to January 14, 2021. The primary focus was on technical and governance
          issues related to staking ETH through Lido, the distribution of LDO tokens, and liquidity management."
      - name: embedding
        type: vector(768)
        description:
          768-dimensional embedding vector representing the semantic meaning of the topic content.
          Used for AI tasks such as semantic search, similarity matching, or clustering.
        example: "[0.005, -0.078, 0.093, ..., 0.009]"
      - name: aggregated_messages
        type: text
        description:
          Concatenated Telegram messages belonging to the DAO–window–topic group.
          Each message is listed in chronological order and prefixed by its UNIX timestamp.
          Provides full context for semantic and qualitative analysis.
        example: |
          [1609048898]: Exactly :) shouldn’t be held by the public, don’t release it
          [1609053778]: Yep....and if this project wouldn't provide them, I will take my stake
          to the inevitable competitor that will....
          [1609084331]: stETH you can get if you stake your ETH tokens using Lido. Visit https://stake.lido.fi
    indexes:
      - "unique (dao_id, window_number, topic_id)"
      - "btree (dao_id, window_start, window_end)"
      - "btree (dao_id)"
      - "btree (window_number)"
      - "btree (start_unix)"
      - "btree (end_unix)"

  - name: github.github_metadata
    description:
      Table storing metadata for GitHub repositories associated with DAOs.
      Each record corresponds to a single repository and includes information such as
      repository description, statistics, and content embeddings. The embeddings
      combine the repository’s textual description and topic keywords, enabling
      semantic similarity searches or relevance-based queries.
      Each repository is linked to a DAO using `dao_id`, which references details in `internal.daos`.
    columns:
      - name: dao_id
        type: integer
        description: "Identifier linking the repository to a DAO. References `internal.daos.id`."
        example: 42
      - name: github_org
        type: text
        description: "GitHub organization name that owns the repository."
        example: "ethereum"
      - name: repo_name
        type: text
        description: "Repository name within the GitHub organization."
        example: "go-ethereum"
      - name: full_name
        type: text
        description: "Full name of the repository in 'org/repo' format."
        example: "ethereum/go-ethereum"
      - name: description
        type: text
        description: "Textual description of the repository provided by maintainers."
        example: "Official Go implementation of the Ethereum protocol."
      - name: html_url
        type: text
        description: "Direct URL to the repository on GitHub."
        example: "https://github.com/ethereum/go-ethereum"
      - name: stargazers_count
        type: integer
        description: "Total number of GitHub stars for the repository."
        example: 45600
      - name: forks_count
        type: integer
        description: "Number of forks of the repository."
        example: 9800
      - name: updated_at
        type: timestamp
        description: "Timestamp indicating the last update to the repository metadata."
        example: "2025-10-28T16:32:00Z"
      - name: readme
        type: text
        description: "Raw content of the repository’s README file."
        example: "# Go Ethereum - Official implementation of the Ethereum protocol."
      - name: embedding
        type: vector(768)
        description:
          768-dimensional vector embedding representing the semantic meaning of the
          repository’s description and topic words. Used for semantic similarity,
          clustering, or AI-assisted retrieval.
        example: "[0.011, -0.032, ..., 0.099]"
      - name: content
        type: jsonb
        description: "Structured JSON content containing additional metadata or extracted fields."
        example:
          {'summary': "balancer/backend provides Balancer's GraphQL API implementation.......",
            'topics': ['GraphQL API',
              'Liquidity Pools',
              'Token Pricing',
              ...]}

  - name: github.github_commits_daos
    description:
      Table storing all commits for DAO-linked GitHub repositories.
      Each commit includes author and committer details, verification info,
      and timestamps. The data enables tracking of project activity,
      developer contributions, and repository evolution over time.
      Commits are semantically connected to their parent repository metadata
      (from `github.github_metadata`) through `dao_id`, allowing enriched analysis
      when combined with repository embeddings.
    columns:
      - name: dao_id
        type: integer
        description: "Identifier linking the commit to a DAO. References `internal.daos.id`."
        example: 42
      - name: github_org
        type: text
        description: "GitHub organization name where the commit’s repository resides."
        example: "ethereum"
      - name: repo_name
        type: text
        description: "Name of the repository associated with this commit."
        example: "go-ethereum"
      - name: base_url
        type: text
        description: "Base GitHub URL of the repository, used to build commit links."
        example: "https://github.com/ethereum/go-ethereum"
      - name: sha
        type: text
        description: "Unique SHA hash identifying the commit."
        example: "a3f1c4b7e923a1e42b9c11b4c01b245e67428f32"
      - name: message
        type: text
        description: "Commit message summarizing the code change."
        example: "Fix RPC timeout handling and dependency upgrade."
      - name: author_name
        type: text
        description: "Full name of the original commit author."
        example: "Vitalik Buterin"
      - name: author_email
        type: text
        description: "Email address of the commit author."
        example: "vitalik@ethereum.org"
      - name: date
        type: timestamptz
        description: "Datetime when the commit was authored (with timezone)."
        example: "2025-10-30T12:45:00Z"
      - name: unix_ts
        type: numeric
        description: "Numeric Unix timestamp representation of the commit time."
        example: 1767117900
      - name: github_username
        type: text
        description: "GitHub username of the author, if available."
        example: "vbuterin"
      - name: profile_url
        type: text
        description: "URL to the GitHub profile of the author."
        example: "https://github.com/vbuterin"
      - name: committer_name
        type: text
        description: "Name of the user who committed the code to the repository."
        example: "Alex Van de Sande"
      - name: committer_email
        type: text
        description: "Email address of the committer."
        example: "alex@ethereum.org"
      - name: html_url
        type: text
        description: "Direct GitHub URL to the specific commit page."
        example: "https://github.com/ethereum/go-ethereum/commit/a3f1c4b7e9"
      - name: verified
        type: boolean
        description: "Indicates if the commit has been cryptographically verified by GitHub."
        example: true
      - name: verification_reason
        type: text
        description: "Reason or status description for the commit’s verification result."
        example: "signed by a verified GPG key"
      - name: parent_sha
        type: text
        description: "SHA of the parent commit, representing commit lineage."
        example: "1e5b2f47e8b9a28e91d5e2e0d6c3a9b62b67c893"

  - name: discourse.posts
    description: "Stores forum posts from Discourse, includes discussions, feedbacks and comments on proposals"
    columns:
      - name: id
        type: integer
        description: "Primary key for each post."
        example: 1020
      - name: username
        type: text
        description: "Forum username of the poster."
        example: "tongnk"
      - name: created_at
        type: timestamp with time zone
        description: "When the post was originally created."
        example: "2020-11-08 23:09:23.303+00"
      - name: cooked
        type: text
        description: "Rendered HTML content of the post (often includes formatting or links)."
        example:
          "<p>The CMC one is pretty cool. I guess maybe a bit more insight into the
          actual content would be helpful. ... 12-15c per word ... 180 articles ...</p>"
      - name: raw
        type: text
        description: "Unprocessed, plain-text/markdown content of the post."
        example:
          "The CMC one is pretty cool. I guess maybe a bit more insight into the
          actual content would be helpful. Given content is a never ending game ..."
      - name: post_number
        type: integer
        description: "Sequential post number within the topic."
        example: 3
      - name: updated_at
        type: timestamp with time zone
        description: "When the post was last updated."
        example: "2020-11-08 23:09:23.303+00"
      - name: reply_count
        type: integer
        description: "Number of direct replies to this post."
        example: 1
      - name: topic_id
        type: integer
        description: "Topic ID to which this post belongs (maps to references in other tables)."
        example: 519
      - name: topic_slug
        type: text
        description: "URL-friendly slug for the topic."
        example: "proposal-balancer-academy-marketing-via-new-user-education"
      - name: topic_title
        type: text
        description: "User-facing title of the topic."
        example: "[Proposal] Balancer Academy - Marketing Via New User Education"
      - name: dao_id
        type: integer
        description: "Internal DAO reference (links to 'internal.daos.id')."
        example: 1
    constraints:
      - primary key (id, dao_id)

  - name: snapshot.daolist
    description: "Stores metadata about each DAO snapshot space. These are rarely relevant for context. Do not confuse this with internal.daos"
    columns:
      - name: dao_id
        type: "character varying(256)"
        description: "Unique snapshot identifier foreign key to 'snapshot.proposallist.dao_id'."
        example: "uniswapgovernance.eth"
      - name: name
        type: "character varying(1024)"
        description: "Human-readable name of the DAO."
        example: "Uniswap"
      - name: about
        type: "character varying(1024)"
        description: "Short description or 'about' text for the DAO."
        example: "Only delegated UNI may be used to vote on proposals..."
      - name: avatar
        type: "character varying(256)"
        description: "URL or IPFS link to the DAO’s avatar/logo."
        example: "ipfs://QmdNntE…"
      - name: website
        type: "character varying(256)"
        description: "Website URL for the DAO."
        example: "https://uniswapfoundation.org"
      - name: twitter
        type: "character varying(256)"
        description: "Twitter handle for the DAO."
        example: "uniswapfnd"
      - name: github
        type: "character varying(256)"
        description: "GitHub username/org for the DAO."
        example: "Uniswap"
      - name: coingecko
        type: "character varying(256)"
        description: "Name/slug on Coingecko for token price tracking."
        example: "uniswap"
      - name: network
        type: "character varying(256)"
        description: "Chain Id. 1 means Ethereum Mainnet."
        example: "1"
      - name: symbol
        type: "character varying(256)"
        description: "Symbol or ticker for the DAO’s token."
        example: "UNI"
      - name: strategies
        type: "jsonb"
        description: "JSON array describing the strategies used for voting."
        example:
          "[{\"name\": \"uni\", \"params\": {\"symbol\": \"UNI\", \"address\": \"0x1f9840…\", \"decimals\": 18}, \"network\": \"1\"}]"
      - name: admins
        type: "character varying(128)[]"
        description: "Array of addresses (in checksum format) with admin privileges."
        example: "{0x0459f4…}"
      - name: members
        type: "character varying(128)[]"
        description: "Array of addresses belonging to the DAO (if membership-only)."
        example: "{}"
      - name: filters
        type: "jsonb"
        description: "JSON object defining filters (e.g. minScore, onlyMembers)."
        example: "{\"minScore\": 10000, \"onlyMembers\": false}"
      - name: voting
        type: "jsonb"
        description: "Voting configuration (e.g., period, quorum, privacy)."
        example: "{\"period\": 432000, \"quorum\": 10000000, \"privacy\": \"\"}"
      - name: categories
        type: "character varying(128)[]"
        description: "Tags/categories associated with this DAO space."
        example: "{defi}"
      - name: validation
        type: "jsonb"
        description: "Rules for validating proposal or voting participants."
        example: "{\"name\": \"basic\", \"params\": {\"minScore\": 10000}}"
      - name: treasuries
        type: "jsonb"
        description: "List of relevant treasury addresses or assets."
        example: "[]"
      - name: followerscount
        type: "integer"
        description: "Number of followers subscribed to the DAO."
        example: "124746"
      - name: proposalcount
        type: "integer"
        description: "Number of proposals created in this DAO space."
        example: "166"
      - name: parent
        type: "jsonb"
        description: "If this DAO is a sub-DAO, references the parent DAO space."
        example: "\"null\""
      - name: children
        type: "jsonb"
        description: "Any sub-DAOs under this DAO."
        example: "[]"
      - name: flagged
        type: "boolean"
        description: "Indicates if this DAO is flagged for moderation."
        example: "false"
      - name: rank
        type: "integer"
        description: "A numeric rank to sort or prioritize DAO listings."
        example: "29"
      - name: verified
        type: "boolean"
        description: "Indicates if the DAO is officially verified."
        example: "true"
      - name: activeproposals
        type: "integer"
        description: "Count of currently active proposals for the DAO."
        example: "1"
      - name: delegateportal
        type: "jsonb"
        description: "JSON object describing delegate portal info (if any)."
        example:
          "{\"delegationApi\": \"https://api.studio.thegraph.com/query/23545/delegates/version/latest\",
           \"delegationType\": \"compound-governor\",
           \"delegationContract\": \"0x1f9840…\"}"

  - name: internal.daos
    description: "Stores core DAO records, mapping them to various discussion or governance platforms."
    columns:
      - name: id
        type: integer
        primary_key: true
        description: "Primary key, unique integer ID for each DAO entry."
        example: 42
      - name: discourse_url
        description: "Base URL or endpoint for the DAO's Discourse forum."
        example: "https://forum.uniswap.org"
      - name: name
        description: "Human-readable name for the DAO."
        example: "Uniswap"
      - name: snapshot_id
        description: "Corresponding Snapshot space ID for the DAO."
        example: "uniswapgovernance.eth"
      - name: coingecko_token_id
        description: "Token ID used by CoinGecko for price and token stats."
        example: "uniswap"
      - name: tally_id
        description: "DAO identifier (if any) used on Tally."
        example: "uniswap.eth"
      - name: discussion_software
        description: "Indicates which forum software is used (e.g., 'discourse')."
        example: "discourse"

    - name: internal.onchain_daos
    description: "Stores configuration and metadata for on-chain DAOs, including contract details, governance parameters, and integration identifiers."
    columns:
      - name: protocol
        type: string
        description: "Name of the underlying governance protocol."
        example: "uni"
      - name: name
        type: string
        description: "Human-readable or shorthand name of the DAO."
        example: "uni"
      - name: chain_id
        type: integer
        description: "Numeric chain ID representing the blockchain network where the DAO contract is deployed."
        example: 1
      - name: contract_address
        type: string
        description: "Blockchain address of the DAO's main governance contract."
        example: "0x408ED6354d4973f66138C91495F2f2FCbd8724C3"
      - name: start_block
        type: bigint
        description: "Block number from which DAO governance tracking begins."
        example: 13059157
      - name: domain
        type: string
        description: "Domain or governance portal used by the DAO."
        example: "gov.uniswap.org"
      - name: vote_parser
        type: string
        description: "Parser logic or format used to interpret voting data from on-chain events."
        example: "standard"
      - name: vote_function
        type: string
        description: "Smart contract function used to retrieve or submit proposals."
        example: "proposals"
      - name: vote_order
        type: jsonb
        description: "Defines the order or structure of vote options (e.g., ['for', 'against', 'abstain'])."
        example: [5, 6, 7]
      - name: has_abstain
        type: boolean
        description: "Indicates whether the DAO includes an 'abstain' voting option."
        example: true
      - name: state_function
        type: string
        description: "Contract function used to fetch the current state of a proposal."
        example: "state"
      - name: has_proxy
        type: boolean
        description: "Indicates whether the DAO uses a proxy contract for governance logic."
        example: true
      - name: tally_id
        type: bigint
        description: "Corresponding identifier for the DAO in Tally (if applicable)."
        example: 2206072050458560434
      - name: dao_id
        type: integer
        description: "Internal reference ID linking this configuration to another DAO record."
        example: 2
      - name: snapshot_id
        type: string
        description: "Snapshot space ID for off-chain governance proposals."
        example: "uniswapgovernance.eth"
      - name: voter_function
        type: string
        description: "Smart contract event or function used to identify voter participation."
        example: "VoteCast_reason"
      - name: proxy_address
        type: string
        description: "Proxy contract address if the DAO uses an upgradeable or delegated setup."
        example: "0x53a328f4086d7c0f1fa19e594c9b842125263026"
      - name: abi
        type: json
        description: "JSON representation of the DAO's ABI for contract interaction."
        example: null
      - name: voting_token_address
        type: string
        description: "Address of the governance token used for voting (if applicable)."
        example: null
      - name: is_active
        type: boolean
        description: "Indicates whether this DAO configuration is currently active for tracking."
        example: true

  - name: onchain_daos.makerdao_governance_polls
    description: "MakerDAO governance polls used in unified_proposals."
    columns:
      - poll_id: text
      - title: text
      - summary: text
      - start_date: bigint
      - end_date: bigint
      - total_mkr_participation: numeric
      - discussion_url: text

  - name: internal.chain_ids
    description: "Canonical mapping from EVM-compatible chain IDs to human-readable network info."
    columns:
      - name: chain_id
        type: bigint
        description: "Numeric Chain ID (EIP-155). Primary identifier for joining with other tables."
        example: 1
      - name: name
        type: text
        description: "Human-readable network name."
        example: "Ethereum Mainnet"
      - name: blockchain
        type: text
        description: "Canonical namespace/slug for the chain or ecosystem."
        example: "ethereum"
      - name: chain_type
        type: text
        description: "Network class (e.g., L1, L2)."
        example: "L1"
      - name: rollup_type
        type: text
        description: "Rollup design if L2 (e.g., optimistic, zk). NULL for L1s."
        example: null
      - name: settlement
        type: text
        description: "Settlement layer for L2s; typically 'ethereum'."
        example: "ethereum"
      - name: native_token_symbol
        type: text
        description: "Ticker symbol of the chain’s native token."
        example: "ETH"
      - name: explorer_link
        type: text
        description: "Block explorer base URL."
        example: "https://etherscan.io"
      - name: wrapped_native_token_address
        type: text
        description: "Address of the canonical wrapped native token (if applicable)."
        example: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

  - name: internal.unified_votelist
    description:
      Materialized view that unifies Snapshot & on-chain DAO votes into a single, consistent
      15-column schema. Use this for vote-level analytics (per-proposal, per-voter, or per-DAO),
      then JOIN to internal.unified_proposals on (proposal = proposal_id AND source).
    columns:
      - name: source
        type: text
        description: "Origin platform: 'snapshot' | 'onchain_daos'."
        example: "snapshot"
      - name: vote_id
        type: text
        description: "Unique vote record identifier (IPFS hash for Snapshot; source-specific for onchain)."
        example: "QmRVAgUxZAdQFVp4f8SKAK7CvWQLCDu5sCvE88mM1zpt1E"
      - name: voter
        type: text
        description: "Voter address (checksum); normalize with LOWER() for comparisons."
        example: "0x911F80D16Ec1B70Db332227b03beb871aC58Ead7"
      - name: created
        type: numeric
        description: "Unix epoch seconds when the vote was cast."
        example: 1595088742
      - name: proposal
        type: text
        description: "FK to internal.unified_proposals.proposal_id (pair with source)."
        example: "0x0020f6…cf542"
      - name: choice
        type: jsonb
        description: "Raw choice payload (Snapshot: numeric or JSON; onchain: coerced as available)."
        example: "1"
      - name: contract_address
        type: text
        description: "On-chain governor/ballot contract address (onchain branch only)."
        example: "0x1234…abcd"
      - name: space
        type: text
        description: "Snapshot space (DAO) identifier (snapshot branch only)."
        example: "balancer.eth"
      - name: dao_name
        type: text
        description: "Human-readable DAO name for onchain branch; may differ from unified_proposals.dao_id."
        example: "MakerDAO"
      - name: app
        type: text
        description: "Client/app that submitted the vote (snapshot branch)."
        example: "snapshot"
      - name: reason
        type: text
        description: "Optional voter-supplied reason text (rarely filled)."
        example: "Pros and cons are well balanced."
      - name: vp_state
        type: text
        description: "Snapshot VP state (e.g., 'final'); NULL for onchain branch."
        example: "final"
      - name: typename
        type: text
        description: "Type label from the source (e.g., 'Vote')."
        example: "Vote"
      - name: vp_by_strategy
        type: "numeric[]"
        description: "Voting power breakdown by strategy (snapshot branch)."
        example: "{4925.3464,0,0}"
      - name: vp
        type: numeric
        description: "Total voting power associated with this vote."
        example: 4925.346413169224

  - name: dune.ens_labels
    description: "Address → ENS mapping used to decorate on-chain addresses with human-readable names."
    columns:
      - name: address
        type: text
        description: "EVM address (contract or EOA)."
        example: "0x1F9840a85d5aF5bf1D1762F925BDADdC4201F984"
      - name: blockchain
        type: text
        description: "Chain namespace for the address."
        example: "ethereum"
      - name: name
        type: text
        description: "Resolved ENS name for the address (if available)."
        example: "uniswap.eth"
  
  - name: internal.socket_snapshot_proposals
    description: "Stores metadata for active Snapshot proposals."
    columns:
      - name: id
        type: text
        description: "Platform-native identifier (Snapshot IPFS/EVM hash, Tally/Aragon/Maker numeric/string cast to text)."
        example: "0x0020f6…cf542"
      - name: title
        type: text
        description: "Human-readable title of the proposal as displayed on Snapshot."
        example: "DeFi Education Fund Temp Check - Options"
      - name: start
        type: integer
        description: "Unix timestamp (in seconds) indicating when voting starts."
        example: 1714465740
      - name: end
        type: integer
        description: "Unix timestamp (in seconds) indicating when voting ends."
        example: 1714897800
      - name: state
        type: text
        description: "Current lifecycle status of the proposal (e.g., 'active', 'closed', 'executed')."
        example: "active"
      - name: snapshot
        type: numeric
        description: "Block number at which voter balances are calculated for this proposal."
        example: 32084342
      - name: author
        type: text
        description: "Wallet address or user ID of the proposal creator."
        example: "0x0020f6…cf542"
      - name: snapshot_id
        type: text
        description: description: "Block number representing the state at which the proposal was created."
        example: 32084342
      - name: snapshot_name
        type: text
        description: "Name or slug of the space (Snapshot namespace) where the proposal was published."
        example: "aave"
      - name: body
        type: text
        description: "Markdown or plaintext content describing the proposal in detail."
        example: "This is a parallel proposal …"
      - name: choices
        type: text[]
        description: "List of selectable voting options presented to voters."
        example: "{'Yes', 'No'}" or "{'for', 'against', 'abstain'}"
      - name: scores
        type: numeric[]
        description: "Vote counts or weights associated with each choice, in the same order as 'choices'."
        example: "{1000000, 0}", "{1000000, 0, 0}"
      - name: active
        type: boolean
        description: "Boolean flag indicating whether the proposal is currently active."
        example: true
      - name: last_updated
        type: integer
        description: "Unix timestamp (in seconds) indicating when the proposal was last updated."
        example: 1714465740

  - name: internal.socket_onchain_proposals
    description: "Stores metadata for active on-chain governance proposals across supported protocols."
    columns:
      - name: id
        type: text
        description: "Platform-native identifier (Snapshot IPFS/EVM hash, Tally/Aragon/Maker numeric/string cast to text)."
        example: "42"
      - name: address
        type: text
        description: "Contract address of the governance module or protocol where the proposal originates."
        example: "0x1234abcd…"
      - name: name
        type: text
        description: "Human-readable name or slug for the protocol or governance space."
        example: "compound"
      - name: title
        type: text
        description: "Title of the on-chain proposal."
        example: "Add USDC Market to Compound v3"
      - name: start
        type: integer
        description: "Unix timestamp (in seconds) indicating when voting begins."
        example: 1714465740
      - name: end
        type: integer
        description: "Unix timestamp (in seconds) indicating when voting ends."
        example: 1714897800
      - name: state
        type: text
        description: "Current lifecycle status of the proposal (e.g., 'active', 'queued', 'executed', 'defeated')."
        example: "active"
      - name: block_number
        type: numeric
        description: "Block number at which the proposal was created or recorded."
        example: 18765432
      - name: author
        type: text
        description: "Address or identifier of the wallet that created the proposal."
        example: "0xabc123…"
      - name: body
        type: text
        description: "Full description or markdown content of the proposal."
        example: "This proposal introduces support for USDC..."
      - name: choices
        type: text[]
        description: "Array of voting options available to participants."
        example: "{'For', 'Against', 'Abstain'}"
      - name: scores
        type: numeric[]
        description: "Vote counts or weights corresponding to each choice, in order."
        example: "{100000, 20000, 5000}"
      - name: active
        type: boolean
        description: "True if the proposal is currently active; false otherwise."
        example: true
      - name: last_updated
        type: integer
        description: "Unix timestamp (in seconds) when the proposal data was last updated."
        example: 1714465740
      - name: last_vote_change
        type: integer
        description: "Unix timestamp (in seconds) of the most recent vote activity on the proposal."
        example: 1714561234

  - name: internal.socket_onchain_votelist
    description: "Stores individual votes on on-chain governance proposals, including voter metadata and vote details."
    columns:
      - name: vote_id
        type: text
        description: "Unique identifier for the vote, typically platform-specific (e.g., transaction hash or indexed ID)."
        example: "0xabc123…"
      - name: voter
        type: text
        description: "Address of the voter who cast the vote."
        example: "0x1234abcd…"
      - name: created
        type: bigint
        description: "Unix timestamp (in seconds) indicating when the vote was cast."
        example: 1714567890
      - name: proposal
        type: text
        description: "Platform-native identifier (Snapshot IPFS/EVM hash, Tally/Aragon/Maker numeric/string cast to text)."
        example: "42"
      - name: choice
        type: jsonb
        description: "Choice selected by the voter. Can represent single or multiple selections, depending on the proposal format."
        example: "{\"1\": 'For'}"
      - name: contract_address
        type: text
        description: "Address of the governance contract where the proposal resides."
        example: "0xDAOContract123…"
      - name: dao_name
        type: text
        description: "Name or slug of the DAO or protocol where the vote took place."
        example: "compound"
      - name: reason
        type: text
        description: "Optional justification or comment provided by the voter when casting the vote."
        example: "Supporting this proposal for ecosystem growth."
      - name: typename
        type: text
        description: "Internal or platform-specific typename associated with the vote record (e.g., for GraphQL or indexing systems)."
        example: "GovernanceVote"
      - name: vp
        type: numeric
        description: "Voting power (in governance units) held by the voter at the time of voting."
        example: 12345.6789
        
  - name: internal.socket_snapshot_votelist
    description: "Stores individual votes on Snapshot active proposals, including voter metadata and vote details."
    columns:
      - name: vote_id
        type: text
        description: "Unique vote record identifier (IPFS hash for Snapshot; source-specific for onchain)."
        example: "QmRVAgUxZAdQFVp4f8SKAK7CvWQLCDu5sCvE88mM1zpt1E"
      - name: voter
        type: text
        description: "Voter address (checksum); normalize with LOWER() for comparisons."
        example: "0x911F80D16Ec1B70Db332227b03beb871aC58Ead7"
      - name: created
        type: numeric
        description: "Unix epoch seconds when the vote was cast."
        example: 1595088742
      - name: proposal
        type: text
        description: "FK to internal.unified_proposals.proposal_id (pair with source)."
        example: "0x0020f6…cf542"
      - name: choice
        type: jsonb
        description: "Raw choice payload (Snapshot: numeric or JSON; onchain: coerced as available)."
        example: "1"
      - name: space
        type: text
        description: "Snapshot space (DAO) identifier (snapshot branch only)."
        example: "balancer.eth"
      - name: app
        type: text
        description: "Client/app that submitted the vote (snapshot branch)."
        example: "snapshot"
      - name: reason
        type: text
        description: "Optional voter-supplied reason text (rarely filled)."
        example: "Pros and cons are well balanced."
      - name: vp_state
        type: text
        description: "Snapshot VP state (e.g., 'final'); NULL for onchain branch."
        example: "final"
      - name: typename
        type: text
        description: "Type label from the source (e.g., 'Vote')."
        example: "Vote"
      - name: vp_by_strategy
        type: "numeric[]"
        description: "Voting power breakdown by strategy (snapshot branch)."
        example: "{4925.3464,0,0}"
      - name: vp
        type: numeric
        description: "Total voting power associated with this vote."
        example: 4925.346413169224

  - name: discord.discord_msg
    description: "Stores messages sent in Discord servers associated with DAOs, including user, channel, and message metadata."
    columns:
      - name: message_id
        type: numeric
        description: "Unique message identifier within the Discord channel."
        example: 1407198394975260745
      - name: dao_id
        type: integer
        description: "Identifier for the associated DAO."
        example: 86
      - name: type
        type: integer
        description: "Discord message type (e.g., default, reply, system)."
        example: 0
      - name: timestamp
        type: timestamp with time zone
        description: "Time the message was sent (UTC)."
        example: "2025-08-19T03:04:01.844+00:00"
      - name: edited_timestamp
        type: timestamp with time zone
        description: "Time the message was last edited, if applicable."
        example: null
      - name: unix_ts
        type: numeric
        description: "Message creation timestamp in Unix epoch seconds."
        example: 1755572641
      - name: channel_id
        type: bigint
        description: "Identifier of the channel where the message was sent."
        example: 611591221474885632
      - name: channel_name
        type: text
        description: "Name of the Discord channel."
        example: "🔗│validators"
      - name: author_id
        type: bigint
        description: "Discord user ID of the message author."
        example: 153718711130259457
      - name: author_username
        type: text
        description: "Username of the message author."
        example: "relik310"
      - name: author_avatar
        type: text
        description: "URL or hash of the user's avatar image."
        example: "4f13c98910c9adf27a25a0997e38f373"
      - name: author_global_name
        type: text
        description: "User's global display name (if different from username)."
        example: "r3lik"
      - name: author_details
        type: json
        description: "Full user metadata as JSON."
        example: '{"id": "153718711130259457", "username": "relik310", "avatar": "4f13c98910c9adf27a25a0997e38f373", "discriminator": "0", "public_flags": 512, "flags": 512, "global_name": "r3lik"}'
      - name: content
        type: text
        description: "Text content of the message."
        example: "Getting this error. We're syncing from scratch. Any ideas?"
      - name: mentions
        type: json
        description: "List of mentioned user objects."
        example: '[]'
      - name: mention_roles
        type: json
        description: "List of mentioned role IDs."
        example: '[]'
      - name: attachments
        type: json
        description: "List of attached files or media."
        example: '[]'
      - name: embeds
        type: json
        description: "Embed metadata (links, previews, etc.)."
        example: '[]'
      - name: flags
        type: integer
        description: "Bitfield of message flags (e.g., crossposted, urgent)."
        example: 0
      - name: components
        type: json
        description: "Components such as buttons or dropdowns."
        example: '[]'
      - name: pinned
        type: boolean
        description: "True if the message is pinned in the channel."
        example: false
      - name: mention_everyone
        type: boolean
        description: "True if message mentions @everyone or @here."
        example: false
      - name: tts
        type: boolean
        description: "True if the message is sent as text-to-speech."
        example: false
      - name: reactions
        type: json
        description: "List of reactions on the message."
        example: null
      - name: message_reference
        type: json
        description: "Reference to the message being replied to (if any)."
        example: '{"type": 0, "channel_id": "611591221474885632", "message_id": "1407090560925302977", "guild_id": "490367152054992913"}'
      - name: referenced_message
        type: json
        description: "Full object of the message being replied to."
        example: '{"type": 0, "content": "hi how long is the epoch sync supposed to take from scratch?"}'
      - name: thread
        type: json
        description: "Thread object if the message starts or belongs to a thread."
        example: null

  - name: github.github_commits
    description: "Stores individual Git commits for tracked repositories, including authorship, commit metadata, and signature verification.
                  It contains commits of only these repositories: 
                  - "https://github.com/HackHumanityOrg/houseofstake.org"
                  - "https://github.com/houseofstake/houseofstake.org"
    columns:
      - name: base_url
        type: text
        description: "Base URL of the GitHub repository."
        example: "https://github.com/HackHumanityOrg/houseofstake.org"
      - name: sha
        type: text
        description: "Unique SHA hash of the commit."
        example: "7bfcd8299d1676d3adfe51b2bfdcf3330d1e4c71"
      - name: message
        type: text
        description: "Commit message."
        example: "Integrate docusaurus-plugin-llms (#15)"
      - name: author_name
        type: text
        description: "Name of the original author of the commit."
        example: "Andrei Voinea"
      - name: author_email
        type: text
        description: "Email of the author."
        example: "8058187+andreivcodes@users.noreply.github.com"
      - name: date
        type: timestamp with time zone
        description: "Timestamp of when the commit was authored."
        example: "2025-08-15T12:16:26+00:00"
      - name: unix_ts
        type: numeric
        description: "Unix epoch seconds corresponding to the commit date."
        example: 1755260186.0
      - name: github_username
        type: text
        description: "GitHub username of the commit author."
        example: "andreivcodes"
      - name: profile_url
        type: text
        description: "URL to the author's GitHub profile."
        example: "https://github.com/andreivcodes"
      - name: committer_name
        type: text
        description: "Name of the user who committed the change (can differ from author)."
        example: "GitHub"
      - name: committer_email
        type: text
        description: "Email of the committer."
        example: "noreply@github.com"
      - name: html_url
        type: text
        description: "Direct URL to the commit on GitHub."
        example: "https://github.com/HackHumanityOrg/houseofstake.org/commit/7bfcd8299d1676d3adfe51b2bfdcf3330d1e4c71"
      - name: verified
        type: boolean
        description: "True if the commit was GPG-signed and verified by GitHub."
        example: true
      - name: verification_reason
        type: text
        description: "Reason for the commit verification status (e.g., 'valid', 'unsigned')."
        example: "valid"
      - name: parent_sha
        type: text
        description: "SHA of the commit's direct parent."
        example: "11ab8027532b8938efd76fff1aaf343dd7e42fec"

  - name: github.github_board
    description: "Represents GitHub issue tracking entries as part of a project board, capturing title, URL, status, and priority.
                  It contains commits of only these repositories: 
                  - "https://github.com/HackHumanityOrg/houseofstake.org"
                  - "https://github.com/houseofstake/houseofstake.org""
    columns:
      - name: title
        type: text
        description: "Title of the GitHub issue or project board card."
        example: "Code of Conduct - Co-Creation Cycle 1 - Gather feedback"
      - name: url
        type: text
        description: "Canonical URL to the GitHub issue, discussion, or project item."
        example: "https://github.com/houseofstake/pm/issues/46"
      - name: status
        type: text
        description: "Current status of the item on the board (e.g., 'Backlog', 'In Progress', 'Done')."
        example: "This Sprint"
      - name: priority
        type: text
        description: "Optional priority label assigned to the item (e.g., 'P0', 'P1')."
        example: "P0"

    

foreign_keys:
  # Active proposals
  - { from: internal.socket_snapshot_proposals.id , to: internal.unified_proposals.proposal_id , when: "source = 'snapshot'" }
  - { from: internal.socket_onchain_proposals.id , to: internal.unified_proposals.proposal_id , when: "source = 'onchain_daos'" }

  # Active proposals ↔ votes
  - { from: internal.socket_onchain_proposals.id , to: internal.socket_onchain_votelist.proposal" }
  - { from: internal.socket_snapshot_proposals.id , to: internal.socket_snapshot_votelist.proposal" }
  
  # Votes ↔ proposals (unified)
  - { from: internal.unified_votelist.proposal , to: internal.unified_proposals.proposal_id , when: "source = 'snapshot'" }
  - { from: internal.unified_votelist.proposal , to: internal.unified_proposals.proposal_id , when: "source = 'onchain_daos'" }
  - { from: internal.unified_votelist.space    , to: internal.unified_proposals.dao_id      , when: "source = 'snapshot'" }
  - { from: internal.unified_votelist.dao_name , to: internal.unified_proposals.dao_id      , when: "source = 'onchain_daos'" }

  # Unified proposals (logical joins by source)
  - { from: internal.unified_proposals.proposal_id , to: snapshot.proposallist.proposal_id          , when: "source = 'snapshot'" }
  - { from: internal.unified_proposals.dao_id      , to: internal.daos.snapshot_id                  , when: "source = 'snapshot'" }
  - { from: internal.unified_proposals.proposal_id , to: tally.tally_data.id                        , when: "source = 'tally'" }
  - { from: internal.unified_proposals.proposal_id , to: aragon.aragon_vt.proposal_id               , when: "source = 'aragon'" }
  - { from: internal.unified_proposals.proposal_id , to: aragon.aragon_multisig.proposal_id         , when: "source = 'aragon'" }
  - { from: internal.unified_proposals.proposal_id , to: onchain_daos.makerdao_governance_polls.poll_id , when: "source = 'onchain_daos'" }

  # Unified embeddings ↔ unified proposals (recommended join for vector search)
  - { from: internal.unified_embeddings.proposal_id , to: internal.unified_proposals.proposal_id }
  - { from: internal.unified_embeddings.source      , to: internal.unified_proposals.source }

  # Discord View ↔ Base tables
  - { from: internal.unified_discord.dao_id,      to: internal.daos.snapshot_id }
  - { from: internal.unified_discord.dao_id,      to: internal.daos.name }

  # Discourse View ↔ Base tables
  - { from: internal.unified_discourse_embeddings.dao_id,   to: internal.daos.snapshot_id }
  - { from: internal.unified_discourse_embeddings.dao_id,   to: internal.daos.name }

  # Telegram View ↔ Base tables
  - { from: internal.unified_telegram.dao_id,     to: internal.daos.snapshot_id }
  - { from: internal.unified_telegram.dao_id,     to: internal.daos.name }
  
Contextual Information:
  - A Delegate is someone who has been given the authority to vote on behalf of another user.
  - Voting on a proposal does in general not give a reward to the delegate.
  - The current voting power of a delegate is the max(vp) of the latest proposal from a given space.
  - A Delegate can vote with their maximum voting power per proposal; the sum(vp) of all votes is not relevant but rather the max(vp) per proposal.

LLM Query Guidance (critical for accuracy & performance):
  - Prefer querying internal.unified_proposals for cross-platform listings/filters.
  - For semantic search: query internal.unified_embeddings with ORDER BY embedding <-> '{prompt_vector}'::vector LIMIT N, then JOIN to internal.unified_proposals using (proposal_id, source).
  - If chunked embeddings are present, either restrict to index = 0 (title/summary) or aggregate top chunks per proposal before joining for context.
  - When time is the primary context, prefer ORDER BY vote_end DESC (or created_at DESC if vote_end is unavailable).
  - Only filter by addresses after normalizing: use LOWER(column) = LOWER('0x…').
  - Avoid filtering on free-text columns unless explicitly required; use full-text ops or embeddings instead.
  - Do not generate destructive statements. Produce a single SELECT. Strip all comments in the final SQL.
"""