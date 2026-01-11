from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter, load_client_config_map_from_file


class GlobalConfigAdapter:
    """Adapter that provides dict-like access to client config values."""

    def __init__(self, adapter: ClientConfigAdapter):
        self._adapter = adapter

    def get(self, key: str, default=None):
        if hasattr(self._adapter, key):
            value = getattr(self._adapter, key)
            return value if value is not None else default
        return default

    def __getattr__(self, item):
        return getattr(self._adapter, item)


try:
    _client_config = load_client_config_map_from_file()
except Exception:
    _client_config = ClientConfigAdapter(ClientConfigMap())


global_config_map = GlobalConfigAdapter(_client_config)
