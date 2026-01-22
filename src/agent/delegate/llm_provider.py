"""LLM Provider abstraction layer for switching between different LLM providers."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import LLMResult

from src.config.common_settings import LOCATION, PROJECT_ID, credentials
from src.config.delegate_agent_settings import AIAgentConfig
from src.utils.model_factory import extract_text_content, requires_global_region

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, model_name: str, temperature: float, **kwargs):
        """Initialize the LLM provider.
        
        Args:
            model_name: Name of the model to use
            temperature: Temperature for generation
            **kwargs: Additional provider-specific parameters
        """
        self.model_name = model_name
        self.temperature = temperature
        self.kwargs = kwargs
        self._llm = None
    
    @abstractmethod
    def _initialize_llm(self) -> Any:
        """Initialize the underlying LLM object."""
        pass
    
    @property
    def llm(self) -> Any:
        """Get the LLM instance, initializing if necessary."""
        if self._llm is None:
            self._llm = self._initialize_llm()
        return self._llm
    
    @abstractmethod
    def generate(self, messages: List[BaseMessage], **kwargs) -> str:
        """Generate text from messages."""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of the provider."""
        pass
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model configuration."""
        return {
            "provider": self.get_provider_name(),
            "model": self.model_name,
            "temperature": self.temperature,
            **self.kwargs
        }

class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider using Vertex AI."""
    
    def __init__(self, model_name: str, temperature: float, **kwargs):
        """Initialize Gemini provider.
        
        Args:
            model_name: Gemini model name
            temperature: Generation temperature
            **kwargs: Additional Gemini-specific parameters
        """
        super().__init__(model_name, temperature, **kwargs)
        
        # Get Gemini-specific settings from config
        gemini_config = AIAgentConfig.get_llm_config("gemini")
        
        # Default Gemini-specific settings (from config or kwargs)
        self.safety_settings = kwargs.get('safety_settings', gemini_config.get('safety_settings', {}))
        self.convert_system_message = kwargs.get('convert_system_message_to_human', 
                                               gemini_config.get('convert_system_message_to_human', True))
    
    def _initialize_llm(self):
        """Initialize Gemini LLM via ChatVertexAI."""
        from langchain_google_vertexai import ChatVertexAI
        
        # Gemini 3 preview models require 'global' region
        location = "global" if requires_global_region(self.model_name) else LOCATION
        
        return ChatVertexAI(
            project=PROJECT_ID,
            location=location,
            credentials=credentials,
            model_name=self.model_name,
            temperature=self.temperature,
            **self.kwargs
        )
    
    def generate(self, messages: List[BaseMessage], **kwargs) -> str:
        """Generate text using Gemini."""
        try:
            response = self.llm.invoke(messages, **kwargs)
            return extract_text_content(response.content)
        except Exception as e:
            logger.error(f"Error generating text with Gemini: {str(e)}")
            raise
    
    def get_provider_name(self) -> str:
        return "gemini"

class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider."""
    
    def __init__(self, model_name: str, temperature: float, openai_api_key: str, **kwargs):
        """Initialize OpenAI provider.
        
        Args:
            model_name: OpenAI model name
            temperature: Generation temperature
            openai_api_key: OpenAI API key
            **kwargs: Additional OpenAI-specific parameters
        """
        super().__init__(model_name, temperature, **kwargs)
        self.openai_api_key = openai_api_key
        
        # Get OpenAI-specific settings from config
        openai_config = AIAgentConfig.get_llm_config("openai")
        
        # Update kwargs with config settings if not provided
        for key, value in openai_config.items():
            if key not in ['model_name', 'temperature'] and key not in kwargs:
                kwargs[key] = value
    
    def _initialize_llm(self):
        """Initialize OpenAI LLM."""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=self.openai_api_key,
            **self.kwargs
        )
    
    def generate(self, messages: List[BaseMessage], **kwargs) -> str:
        """Generate text using OpenAI."""
        try:
            response = self.llm.invoke(messages, **kwargs)
            return extract_text_content(response.content)
        except Exception as e:
            logger.error(f"Error generating text with OpenAI: {str(e)}")
            raise
    
    def get_provider_name(self) -> str:
        return "openai"



class LLMProviderFactory:
    """Factory for creating LLM providers."""
    
    _providers = {
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
    }
    
    @classmethod
    def create_provider(
        cls,
        provider_name: str,
        model_name: str = None,
        temperature: float = None,
        **kwargs
    ) -> BaseLLMProvider:
        """Create an LLM provider instance.
        
        Args:
            provider_name: Name of the provider ("gemini", "openai", "anthropic")
            model_name: Model name (will use config default if not provided)
            temperature: Temperature (will use config default if not provided)
            **kwargs: Provider-specific parameters
            
        Returns:
            Configured LLM provider instance
        """
        if provider_name not in cls._providers:
            raise ValueError(f"Unsupported provider: {provider_name}. Supported providers: {list(cls._providers.keys())}")
        
        # Get default values from config if not provided
        if model_name is None:
            # First try to get from YAML config, then fall back to environment variable
            model_name = AIAgentConfig.get_provider_model_name(provider_name)
            if not model_name:
                model_name = AIAgentConfig.get_model_name(provider_name)
        
        if temperature is None:
            temperature = AIAgentConfig.get_temperature()
        
        # Get API key based on provider
        if provider_name == "gemini":
            # API key is not used for Vertex AI, credentials are used instead.
            pass
        elif provider_name == "openai":
            api_key = kwargs.get('openai_api_key') or AIAgentConfig.get_openai_api_key()
            kwargs['openai_api_key'] = api_key
        
        provider_class = cls._providers[provider_name]
        return provider_class(model_name, temperature, **kwargs)
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type):
        """Register a new provider class.
        
        Args:
            name: Provider name
            provider_class: Provider class that inherits from BaseLLMProvider
        """
        if not issubclass(provider_class, BaseLLMProvider):
            raise ValueError("Provider class must inherit from BaseLLMProvider")
        cls._providers[name] = provider_class
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available provider names."""
        return list(cls._providers.keys())

class LLMManager:
    """Manager for LLM operations with provider abstraction."""
    
    def __init__(self, provider_name: str = "gemini", llm_timeout: int = 60, **kwargs):
        """Initialize LLM manager.
        
        Args:
            provider_name: Name of the LLM provider to use
            llm_timeout: Timeout in seconds for LLM requests
            **kwargs: Provider-specific configuration
        """
        # Add timeout to kwargs if not already present
        if 'timeout' not in kwargs:
            kwargs['timeout'] = llm_timeout
            
        self.provider = LLMProviderFactory.create_provider(provider_name, **kwargs)
        self.provider_name = provider_name
    
    @staticmethod
    def detect_provider() -> str:
        """Automatically detect which LLM provider to use based on available API keys.
        
        Returns:
            Provider name ("openai" or "gemini")
            
        Raises:
            ValueError: If no API keys are available
        """
        has_openai = bool(os.getenv("OPENAI_API_KEY"))
        has_gemini = bool(os.getenv("GOOGLE_API_KEY"))
        
        if has_openai and has_gemini:
            # Both available, use OpenAI as default
            return "openai"
        elif has_openai:
            return "openai"
        elif has_gemini:
            return "gemini"
        else:
            raise ValueError("No API keys found. Please set either OPENAI_API_KEY or GOOGLE_API_KEY environment variable.")
    
    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of providers with available API keys."""
        available = []
        if os.getenv("OPENAI_API_KEY"):
            available.append("openai")
        if os.getenv("GOOGLE_API_KEY"):
            available.append("gemini")
        return available
    
    def generate_text(self, messages: List[BaseMessage], **kwargs) -> str:
        """Generate text using the configured provider.
        
        Args:
            messages: List of messages to send to the LLM
            **kwargs: Additional generation parameters
            
        Returns:
            Generated text
        """
        return self.provider.generate(messages, **kwargs)
    
    def generate_from_prompt(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """Generate text from a simple prompt.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional generation parameters
            
        Returns:
            Generated text
        """
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        return self.generate_text(messages, **kwargs)
    
    def switch_provider(self, provider_name: str, **kwargs):
        """Switch to a different LLM provider.
        
        Args:
            provider_name: Name of the new provider
            **kwargs: Provider-specific configuration
        """
        self.provider = LLMProviderFactory.create_provider(provider_name, **kwargs)
        self.provider_name = provider_name
        logger.info(f"Switched to {provider_name} provider")
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current provider."""
        return {
            "provider_name": self.provider_name,
            "model_info": self.provider.get_model_info()
        }
    
 