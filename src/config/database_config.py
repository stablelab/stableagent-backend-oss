"""
Database configuration and validation utilities.

This module provides centralized database configuration management with
proper validation and error handling for missing environment variables.
"""

import os
from typing import Optional, Dict, Any
from src.utils.logger import logger


class DatabaseConfig:
    """Centralized database configuration with validation."""
    
    def __init__(self):
        self._config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load database configuration from environment variables."""
        # Support DATABASE_URL with percent-encoded passwords, e.g.:
        # postgresql://user:enc_pass@host:5432/db?sslmode=require
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            from urllib.parse import urlparse, unquote, parse_qs
            parsed = urlparse(db_url)
            query = parse_qs(parsed.query)
            sslmode = query.get("sslmode", [os.environ.get("PGSSLMODE", "require")])[0]
            return {
                'host': parsed.hostname,
                'port': parsed.port or int(os.environ.get("DATABASE_PORT", "5432")),
                'database': parsed.path.lstrip('/') if parsed.path else None,
                'user': parsed.username,
                'password': unquote(parsed.password or ""),
                'connect_timeout': int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
                'statement_timeout_ms': int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "60000")),
                'application_name': os.environ.get("DB_APPLICATION_NAME", "stableagent-backend"),
                'sslmode': sslmode,
            }
        else:
            return {
                'host': os.environ.get("DATABASE_HOST"),
                'port': os.environ.get("DATABASE_PORT", "5432"),
                'database': os.environ.get("DATABASE_NAME"),
                'user': os.environ.get("DATABASE_USER"),
                'password': os.environ.get("DATABASE_PASSWORD"),
                'connect_timeout': int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
                'statement_timeout_ms': int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "60000")),
                'application_name': os.environ.get("DB_APPLICATION_NAME", "stableagent-backend"),
            }
    
    def _validate_config(self) -> None:
        """Validate that all required configuration is present."""
        required_fields = ['host', 'database', 'user', 'password']
        missing_fields = []
        
        for field in required_fields:
            if not self._config.get(field):
                missing_fields.append(f"DATABASE_{field.upper()}")
        
        if missing_fields:
            error_msg = f"Missing required database environment variables: {', '.join(missing_fields)}"
            logger.error("DatabaseConfig: %s", error_msg)
            raise RuntimeError(error_msg)
        
        # Validate port is numeric
        try:
            self._config['port'] = int(self._config['port'])
        except (ValueError, TypeError):
            raise RuntimeError("DATABASE_PORT must be a valid integer")
    
    def get_connection_params(self) -> Dict[str, Any]:
        """Get connection parameters for psycopg2.

        Adds reasonable defaults for SSL and TCP keepalives, and forces IPv4 by
        setting hostaddr when the host looks like an IPv4 literal or when
        DATABASE_HOSTADDR is explicitly provided.
        """
        params: Dict[str, Any] = {
            'host': self._config['host'],
            'port': self._config['port'],
            'database': self._config['database'],
            'user': self._config['user'],
            'password': self._config['password'],
            'connect_timeout': self._config['connect_timeout'],
            'application_name': self._config['application_name'],
            'sslmode': os.environ.get("PGSSLMODE", "require"),
            # TCP keepalives (seconds)
            'keepalives': int(os.environ.get('PG_KEEPALIVES', '1')),
            'keepalives_idle': int(os.environ.get('PG_KEEPALIVES_IDLE', '30')),
            'keepalives_interval': int(os.environ.get('PG_KEEPALIVES_INTERVAL', '10')),
            'keepalives_count': int(os.environ.get('PG_KEEPALIVES_COUNT', '5')),
            'target_session_attrs': os.environ.get('PG_TARGET_SESSION_ATTRS', 'read-write'),
        }

        # Optional hostaddr to force IPv4
        env_hostaddr = os.environ.get("DATABASE_HOSTADDR")
        if env_hostaddr:
            params['hostaddr'] = env_hostaddr
        else:
            host = self._config['host'] or ""
            if host and all(part.isdigit() and 0 <= int(part) <= 255 for part in host.split('.') if part != '') and host.count('.') == 3:
                params['hostaddr'] = host

        return params
    
    def get_statement_timeout_ms(self) -> int:
        """Get the statement timeout in milliseconds."""
        return self._config['statement_timeout_ms']
    
    @property
    def host(self) -> str:
        return self._config['host']
    
    @property
    def port(self) -> int:
        return self._config['port']
    
    @property
    def database(self) -> str:
        return self._config['database']
    
    @property
    def user(self) -> str:
        return self._config['user']


# Global database configuration instance
db_config = DatabaseConfig()


def get_database_config() -> DatabaseConfig:
    """Get the global database configuration instance."""
    return db_config


def validate_database_environment() -> bool:
    """
    Validate database environment variables are properly set.
    
    Returns:
        True if all required variables are set, False otherwise.
    """
    try:
        DatabaseConfig()
        return True
    except ValueError as e:
        logger.error("Database environment validation failed: %s", e)
        return False


def get_connection_string() -> str:
    """
    Get a connection string for debugging purposes (password redacted).
    
    Returns:
        A connection string with the password redacted.
    """
    config = get_database_config()
    return f"postgresql://{config.user}:***@{config.host}:{config.port}/{config.database}"
