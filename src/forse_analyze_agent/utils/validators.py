import os


def get_required_env(env_name) -> str:
    base_url = os.environ.get(f"{env_name}")

    if not base_url:
        raise ValueError(f"{env_name} environment variable is required.")
    return base_url
