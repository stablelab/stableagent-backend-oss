import os
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class AIAgentConfig:
    """Configuration for AI components."""
    
    _config = None
    _config_path = Path(__file__).parent / "agent_config.yaml"
    
    @staticmethod
    def get_google_api_key() -> str:
        """Get Google API key from environment variables."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        return api_key
    
    @staticmethod
    def get_openai_api_key() -> str:
        """Get OpenAI API key from environment variables."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        return api_key
    
        
    @staticmethod
    def get_model_name(llm_type: str = "gemini") -> str:
        """Get the model name from environment variables."""
        if llm_type == "openai":
            model_name = os.getenv("OPENAI_MODEL_NAME")
            if not model_name:
                raise ValueError("OPENAI_MODEL_NAME environment variable is not set")
            return model_name

        else:  # gemini
            model_name = os.getenv("VERTEX_DEFAULT_MODEL")
            if not model_name:
                raise ValueError("VERTEX_DEFAULT_MODEL environment variable is not set")
            return model_name
    
    @classmethod
    def _load_config(cls) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if cls._config is None:
            try:
                with open(cls._config_path, 'r') as f:
                    cls._config = yaml.safe_load(f)
                if cls._config is None:
                    raise ValueError("Configuration file is empty or invalid")
            except FileNotFoundError:
                raise FileNotFoundError(f"Configuration file not found at {cls._config_path}. Please ensure agent_config.yaml exists.")
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing YAML configuration file: {e}")
            except Exception as e:
                raise RuntimeError(f"Unexpected error loading configuration: {e}")
        return cls._config
    
    # LLM Configuration
    @classmethod
    def get_temperature(cls) -> float:
        """Get temperature from YAML config."""
        config = cls._load_config()
        return config['llm']['temperature']
    
    @classmethod
    def get_max_tokens(cls) -> int:
        """Get max tokens from YAML config."""
        config = cls._load_config()
        return config['llm'].get('max_tokens', 2000)
    
    @classmethod
    def get_llm_config(cls, provider_name: str = "gemini") -> Dict[str, Any]:
        """Get LLM configuration for a specific provider.
        
        Args:
            provider_name: Name of the provider ("gemini", "openai", "anthropic")
            
        Returns:
            Dictionary with provider-specific configuration
        """
        config = cls._load_config()
        llm_config = config['llm']
        
        # Get global settings
        provider_config = {
            'temperature': llm_config.get('temperature', 0.2),
            'max_tokens': llm_config.get('max_tokens', 2000)
        }
        
        # Get provider-specific settings if available
        if 'providers' in llm_config and provider_name in llm_config['providers']:
            provider_specific = llm_config['providers'][provider_name]
            provider_config.update(provider_specific)
        
        return provider_config
    
    @classmethod
    def get_provider_model_name(cls, provider_name: str) -> str:
        """Get model name for a specific provider from YAML config.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Model name for the provider
        """
        config = cls._load_config()
        llm_config = config['llm']
        
        # Check if provider-specific model name is configured
        if 'providers' in llm_config and provider_name in llm_config['providers']:
            return llm_config['providers'][provider_name].get('model_name', '')
        
        return ''
    
    # Similarity search configuration
    @classmethod
    def get_similarity_limit(cls) -> int:
        """Get similarity limit."""
        config = cls._load_config()
        return config['similarity']['default_limit']
    
    @classmethod
    def get_similarity_threshold(cls) -> float:
        """Get similarity threshold."""
        config = cls._load_config()
        return config['similarity']['threshold']
    
    @classmethod
    def get_max_content_preview(cls) -> int:
        """Get maximum content preview length."""
        config = cls._load_config()
        return config['similarity']['max_content_preview']
    
    # Analysis configuration
    @classmethod
    def get_max_reasoning_length(cls) -> int:
        """Get maximum reasoning length."""
        config = cls._load_config()
        return config['analysis']['max_reasoning_length']
    
    @classmethod
    def get_max_similar_items(cls) -> int:
        """Get maximum similar items to show."""
        config = cls._load_config()
        return config['analysis']['max_similar_items']
    
    # System prompt template
    @classmethod
    def get_system_prompt_template(cls) -> str:
        """Get system prompt template."""
        config = cls._load_config()
        return config['system_prompt']
    
    # Content formatting templates
    @classmethod
    def get_proposal_format_templates(cls) -> Dict[str, str]:
        """Get proposal format templates."""
        config = cls._load_config()
        return config['formatting']['proposal_templates']
    
    @classmethod
    def get_similar_content_templates(cls) -> Dict[str, str]:
        """Get similar content templates."""
        config = cls._load_config()
        return config['formatting']['similar_content_templates']
    
    @classmethod
    def get_content_item_templates(cls) -> Dict[str, str]:
        """Get content item templates."""
        config = cls._load_config()
        return config['formatting']['content_item_templates']
    
    # Keyword extraction configuration
    @classmethod
    def get_keywords(cls) -> Dict[str, List[str]]:
        """Get keywords for content matching."""
        config = cls._load_config()
        return config['keywords']
    
    # Fallback similarity scores for general context
    @classmethod
    def get_fallback_similarity_scores(cls) -> Dict[str, float]:
        """Get fallback similarity scores."""
        config = cls._load_config()
        return config['fallback']['similarity_scores']
    
    @classmethod
    def get_max_keywords(cls) -> int:
        """Get maximum number of keywords to extract."""
        config = cls._load_config()
        return config['fallback']['max_keywords']
    
    # Convenience methods
    @classmethod
    def get_system_prompt(cls, proposal_text: str, context_text: str, voting_options: List[str], max_reasoning_length: int = None) -> str:
        """Generate the system prompt with the given parameters."""
        if max_reasoning_length is None:
            max_reasoning_length = cls.get_max_reasoning_length()
            
        voting_options_text = ", ".join(voting_options)
        template = cls.get_system_prompt_template()
        
        return template.format(
            proposal_text=proposal_text,
            context_text=context_text,
            voting_options_text=voting_options_text,
            max_reasoning_length=max_reasoning_length
        )
    
    @classmethod
    def get_proposal_format_template(cls, source: str) -> str:
        """Get the proposal format template for the given source."""
        templates = cls.get_proposal_format_templates()
        return templates[source]
    
    @classmethod
    def get_similar_content_template(cls, content_type: str) -> str:
        """Get the similar content template for the given content type."""
        templates = cls.get_similar_content_templates()
        return templates[content_type]
    
    @classmethod
    def get_content_item_template(cls, item_type: str) -> str:
        """Get the content item template for the given item type."""
        templates = cls.get_content_item_templates()
        return templates[item_type]
    
    @classmethod
    def get_all_keywords(cls) -> List[str]:
        """Get all keywords for content matching."""
        keywords = cls.get_keywords()
        return keywords['governance'] + keywords['technical']
    
    @classmethod
    def get_fallback_similarity_score(cls, content_type: str) -> float:
        """Get the fallback similarity score for the given content type."""
        scores = cls.get_fallback_similarity_scores()
        return scores[content_type]
    
    # Two-stage analysis configuration
    @staticmethod
    def is_two_stage_enabled() -> bool:
        """Check if two-stage analysis is enabled."""
        return os.getenv("TWO_STAGE_ANALYSE", "off").lower() in ["on", "true", "1", "enabled"]
    
    @classmethod
    def get_two_stage_config(cls) -> Dict[str, Any]:
        """Get two-stage analysis configuration."""
        config = cls._load_config()
        
        # Default two-stage config
        default_config = {
            'enabled': False,
            'cache_ttl_hours': 3,
            'fallback_to_legacy': True,
            'user_overlay_model': 'gemini-1.5-flash',
            'max_retries': 1
        }
        
        # Get config from YAML if available
        two_stage_config = config.get('two_stage', {})
        
        # Merge with defaults
        final_config = {**default_config, **two_stage_config}
        
        # Override enabled status from environment variable
        final_config['enabled'] = cls.is_two_stage_enabled()
        
        return final_config