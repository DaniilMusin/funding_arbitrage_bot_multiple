#!/usr/bin/env python3
"""
Скрипт для проверки подключения ко всем поддерживаемым биржам в Hummingbot
"""

import asyncio
import os
import sys
from typing import Dict, List, Optional

# Добавляем путь к hummingbot
sys.path.append(os.path.join(os.path.dirname(__file__), 'hummingbot'))

from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.core.data_type.common import OrderType, PositionMode, TradeType
from hummingbot.core.utils.async_utils import safe_ensure_future


class ExchangeConnectionChecker:
    def __init__(self):
        self.client_config_map = ClientConfigAdapter()
        self.connections_status = {}
        
    async def check_bybit_perpetual(self) -> Dict[str, any]:
        """Проверка подключения к Bybit Perpetual"""
        try:
            from hummingbot.connector.derivative.bybit_perpetual.bybit_perpetual_derivative import BybitPerpetualDerivative
            
            # Получаем API ключи из переменных окружения
            api_key = os.getenv("BYBIT_PERPETUAL_API_KEY")
            secret_key = os.getenv("BYBIT_PERPETUAL_SECRET_KEY")
            
            if not api_key or not secret_key:
                return {
                    "status": "error",
                    "message": "API ключи для Bybit Perpetual не настроены. Установите переменные окружения BYBIT_PERPETUAL_API_KEY и BYBIT_PERPETUAL_SECRET_KEY"
                }
            
            # Создаем коннектор
            connector = BybitPerpetualDerivative(
                client_config_map=self.client_config_map,
                bybit_perpetual_api_key=api_key,
                bybit_perpetual_secret_key=secret_key,
                trading_required=False  # Только для проверки подключения
            )
            
            # Проверяем подключение
            await connector.start_network()
            
            # Проверяем время сервера
            server_time = await connector._api_request(
                path_url="v5/market/time",
                is_auth_required=False
            )
            
            await connector.stop_network()
            
            return {
                "status": "success",
                "message": f"Подключение к Bybit Perpetual успешно. Время сервера: {server_time.get('result', {}).get('timeSecond', 'N/A')}",
                "server_time": server_time.get('result', {}).get('timeSecond', 'N/A')
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к Bybit Perpetual: {str(e)}"
            }
    
    async def check_kucoin_perpetual(self) -> Dict[str, any]:
        """Проверка подключения к KuCoin Perpetual"""
        try:
            from hummingbot.connector.derivative.kucoin_perpetual.kucoin_perpetual_derivative import KucoinPerpetualDerivative
            
            # Получаем API ключи из переменных окружения
            api_key = os.getenv("KUCOIN_PERPETUAL_API_KEY")
            secret_key = os.getenv("KUCOIN_PERPETUAL_SECRET_KEY")
            passphrase = os.getenv("KUCOIN_PERPETUAL_PASSPHRASE")
            
            if not api_key or not secret_key or not passphrase:
                return {
                    "status": "error",
                    "message": "API ключи для KuCoin Perpetual не настроены. Установите переменные окружения KUCOIN_PERPETUAL_API_KEY, KUCOIN_PERPETUAL_SECRET_KEY и KUCOIN_PERPETUAL_PASSPHRASE"
                }
            
            # Создаем коннектор
            connector = KucoinPerpetualDerivative(
                client_config_map=self.client_config_map,
                kucoin_perpetual_api_key=api_key,
                kucoin_perpetual_secret_key=secret_key,
                kucoin_perpetual_passphrase=passphrase,
                trading_required=False  # Только для проверки подключения
            )
            
            # Проверяем подключение
            await connector.start_network()
            
            # Проверяем время сервера
            server_time = await connector._api_request(
                path_url="api/v1/timestamp",
                is_auth_required=False
            )
            
            await connector.stop_network()
            
            return {
                "status": "success",
                "message": f"Подключение к KuCoin Perpetual успешно. Время сервера: {server_time.get('data', 'N/A')}",
                "server_time": server_time.get('data', 'N/A')
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к KuCoin Perpetual: {str(e)}"
            }
    
    async def check_binance_spot(self) -> Dict[str, any]:
        """Проверка подключения к Binance Spot"""
        try:
            from hummingbot.connector.exchange.binance.binance_exchange import BinanceExchange
            
            # Получаем API ключи из переменных окружения
            api_key = os.getenv("BINANCE_API_KEY")
            secret_key = os.getenv("BINANCE_API_SECRET")
            
            if not api_key or not secret_key:
                return {
                    "status": "error",
                    "message": "API ключи для Binance Spot не настроены. Установите переменные окружения BINANCE_API_KEY и BINANCE_API_SECRET"
                }
            
            # Создаем коннектор
            connector = BinanceExchange(
                client_config_map=self.client_config_map,
                binance_api_key=api_key,
                binance_api_secret=secret_key,
                trading_required=False
            )
            
            # Проверяем подключение
            await connector.start_network()
            
            # Проверяем время сервера
            server_time = await connector._api_request(
                path_url="api/v3/time",
                is_auth_required=False
            )
            
            await connector.stop_network()
            
            return {
                "status": "success",
                "message": f"Подключение к Binance Spot успешно. Время сервера: {server_time.get('serverTime', 'N/A')}",
                "server_time": server_time.get('serverTime', 'N/A')
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к Binance Spot: {str(e)}"
            }
    
    async def check_okx_spot(self) -> Dict[str, any]:
        """Проверка подключения к OKX Spot"""
        try:
            from hummingbot.connector.exchange.okx.okx_exchange import OkxExchange
            
            # Получаем API ключи из переменных окружения
            api_key = os.getenv("OKX_API_KEY")
            secret_key = os.getenv("OKX_SECRET_KEY")
            passphrase = os.getenv("OKX_PASSPHRASE")
            
            if not api_key or not secret_key or not passphrase:
                return {
                    "status": "error",
                    "message": "API ключи для OKX Spot не настроены. Установите переменные окружения OKX_API_KEY, OKX_SECRET_KEY и OKX_PASSPHRASE"
                }
            
            # Создаем коннектор
            connector = OkxExchange(
                client_config_map=self.client_config_map,
                okx_api_key=api_key,
                okx_secret_key=secret_key,
                okx_passphrase=passphrase,
                trading_required=False
            )
            
            # Проверяем подключение
            await connector.start_network()
            
            # Проверяем время сервера
            server_time = await connector._api_request(
                path_url="api/v5/public/time",
                is_auth_required=False
            )
            
            await connector.stop_network()
            
            return {
                "status": "success",
                "message": f"Подключение к OKX Spot успешно. Время сервера: {server_time.get('data', [{}])[0].get('ts', 'N/A')}",
                "server_time": server_time.get('data', [{}])[0].get('ts', 'N/A')
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к OKX Spot: {str(e)}"
            }
    
    async def check_all_exchanges(self):
        """Проверка всех поддерживаемых бирж"""
        print("🔍 Проверка подключения ко всем биржам...")
        print("=" * 60)
        
        # Список всех проверок
        checks = [
            ("Bybit Perpetual", self.check_bybit_perpetual),
            ("KuCoin Perpetual", self.check_kucoin_perpetual),
            ("Binance Spot", self.check_binance_spot),
            ("OKX Spot", self.check_okx_spot),
        ]
        
        results = {}
        
        for exchange_name, check_func in checks:
            print(f"\n📡 Проверка {exchange_name}...")
            try:
                result = await check_func()
                results[exchange_name] = result
                
                if result["status"] == "success":
                    print(f"✅ {exchange_name}: {result['message']}")
                else:
                    print(f"❌ {exchange_name}: {result['message']}")
                    
            except Exception as e:
                error_result = {
                    "status": "error",
                    "message": f"Неожиданная ошибка: {str(e)}"
                }
                results[exchange_name] = error_result
                print(f"❌ {exchange_name}: {error_result['message']}")
        
        # Выводим итоговую статистику
        print("\n" + "=" * 60)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        
        successful = sum(1 for result in results.values() if result["status"] == "success")
        total = len(results)
        
        print(f"✅ Успешно подключено: {successful}/{total}")
        print(f"❌ Ошибки подключения: {total - successful}/{total}")
        
        if successful == total:
            print("\n🎉 Все биржи подключены успешно!")
        else:
            print(f"\n⚠️  {total - successful} бирж(и) не удалось подключить.")
            print("\nДля настройки API ключей используйте переменные окружения:")
            print("- BYBIT_PERPETUAL_API_KEY, BYBIT_PERPETUAL_SECRET_KEY")
            print("- KUCOIN_PERPETUAL_API_KEY, KUCOIN_PERPETUAL_SECRET_KEY, KUCOIN_PERPETUAL_PASSPHRASE")
            print("- BINANCE_API_KEY, BINANCE_API_SECRET")
            print("- OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE")
        
        return results


async def main():
    """Основная функция"""
    checker = ExchangeConnectionChecker()
    await checker.check_all_exchanges()


if __name__ == "__main__":
    asyncio.run(main())