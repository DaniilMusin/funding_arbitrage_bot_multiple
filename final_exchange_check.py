#!/usr/bin/env python3
"""
Финальная версия скрипта для проверки подключения к биржам
"""

import asyncio
import aiohttp
import time
import json
from typing import Dict, Optional


class FinalExchangeChecker:
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        # Создаем сессию с правильными заголовками и без Brotli
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',  # Убираем brotli
            'Connection': 'keep-alive',
        }
        
        timeout = aiohttp.ClientTimeout(total=10)
        connector = aiohttp.TCPConnector(ssl=False)  # Отключаем SSL проверку для тестирования
        self.session = aiohttp.ClientSession(
            headers=headers, 
            timeout=timeout,
            connector=connector
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_bybit_perpetual(self) -> Dict[str, any]:
        """Проверка подключения к Bybit Perpetual"""
        try:
            # Попробуем несколько вариантов URL и заголовков
            urls = [
                "https://api.bybit.com/v5/market/time",
                "https://api-testnet.bybit.com/v5/market/time"
            ]
            
            headers_variants = [
                {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                    'Referer': 'https://www.bybit.com/',
                },
                {
                    'User-Agent': 'Hummingbot/1.0',
                    'Accept': 'application/json',
                }
            ]
            
            for url in urls:
                for headers in headers_variants:
                    try:
                        async with self.session.get(url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("retCode") == 0:
                                    return {
                                        "status": "success",
                                        "message": f"Подключение к Bybit Perpetual успешно (через {url}). Время сервера: {data.get('result', {}).get('timeSecond', 'N/A')}",
                                        "server_time": data.get('result', {}).get('timeSecond', 'N/A')
                                    }
                    except:
                        continue
            
            return {
                "status": "error",
                "message": "Не удалось подключиться к Bybit Perpetual (требуется специальная настройка)"
            }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к Bybit Perpetual: {str(e)}"
            }
    
    async def check_kucoin_perpetual(self) -> Dict[str, any]:
        """Проверка подключения к KuCoin Perpetual"""
        try:
            url = "https://api-futures.kucoin.com/api/v1/timestamp"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == "200000":
                        return {
                            "status": "success",
                            "message": f"Подключение к KuCoin Perpetual успешно. Время сервера: {data.get('data', 'N/A')}",
                            "server_time": data.get('data', 'N/A')
                        }
                    else:
                        return {
                            "status": "error",
                            "message": f"Ошибка API KuCoin: {data.get('msg', 'Unknown error')}"
                        }
                else:
                    return {
                        "status": "error",
                        "message": f"HTTP ошибка {response.status}: {response.reason}"
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к KuCoin Perpetual: {str(e)}"
            }
    
    async def check_binance_spot(self) -> Dict[str, any]:
        """Проверка подключения к Binance Spot"""
        try:
            # Попробуем альтернативные URL для Binance
            urls = [
                "https://api.binance.com/api/v3/time",
                "https://api1.binance.com/api/v3/time",
                "https://api2.binance.com/api/v3/time",
                "https://api3.binance.com/api/v3/time",
                "https://testnet.binance.vision/api/v3/time"
            ]
            
            for url in urls:
                try:
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "serverTime" in data:
                                return {
                                    "status": "success",
                                    "message": f"Подключение к Binance Spot успешно (через {url}). Время сервера: {data.get('serverTime', 'N/A')}",
                                    "server_time": data.get('serverTime', 'N/A')
                                }
                except:
                    continue
            
            return {
                "status": "error",
                "message": "Не удалось подключиться к Binance Spot (возможно, блокировка по региону)"
            }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к Binance Spot: {str(e)}"
            }
    
    async def check_okx_spot(self) -> Dict[str, any]:
        """Проверка подключения к OKX Spot"""
        try:
            url = "https://www.okx.com/api/v5/public/time"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == "0":
                        server_time = data.get('data', [{}])[0].get('ts', 'N/A')
                        return {
                            "status": "success",
                            "message": f"Подключение к OKX Spot успешно. Время сервера: {server_time}",
                            "server_time": server_time
                        }
                    else:
                        return {
                            "status": "error",
                            "message": f"Ошибка API OKX: {data.get('msg', 'Unknown error')}"
                        }
                else:
                    return {
                        "status": "error",
                        "message": f"HTTP ошибка {response.status}: {response.reason}"
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к OKX Spot: {str(e)}"
            }
    
    async def check_kraken_spot(self) -> Dict[str, any]:
        """Проверка подключения к Kraken Spot"""
        try:
            url = "https://api.kraken.com/0/public/Time"
            
            # Используем заголовки без Brotli
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',  # Убираем brotli
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("error") == []:
                        server_time = data.get('result', {}).get('unixtime', 'N/A')
                        return {
                            "status": "success",
                            "message": f"Подключение к Kraken Spot успешно. Время сервера: {server_time}",
                            "server_time": server_time
                        }
                    else:
                        return {
                            "status": "error",
                            "message": f"Ошибка API Kraken: {data.get('error', 'Unknown error')}"
                        }
                else:
                    return {
                        "status": "error",
                        "message": f"HTTP ошибка {response.status}: {response.reason}"
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к Kraken Spot: {str(e)}"
            }
    
    async def check_gate_io_spot(self) -> Dict[str, any]:
        """Проверка подключения к Gate.io Spot"""
        try:
            url = "https://api.gateio.ws/api/v4/spot/time"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "server_time" in data:
                        return {
                            "status": "success",
                            "message": f"Подключение к Gate.io Spot успешно. Время сервера: {data.get('server_time', 'N/A')}",
                            "server_time": data.get('server_time', 'N/A')
                        }
                    else:
                        return {
                            "status": "error",
                            "message": "Неожиданный формат ответа от Gate.io"
                        }
                else:
                    return {
                        "status": "error",
                        "message": f"HTTP ошибка {response.status}: {response.reason}"
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к Gate.io Spot: {str(e)}"
            }
    
    async def check_htx_spot(self) -> Dict[str, any]:
        """Проверка подключения к HTX (Huobi) Spot"""
        try:
            # Попробуем несколько URL для HTX
            urls = [
                "https://api.huobi.pro/v2/reference/currencies",
                "https://api-aws.huobi.pro/v2/reference/currencies",
                "https://api.huobi.pro/v1/common/timestamp"
            ]
            
            for url in urls:
                try:
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("status") == "ok" or "data" in data:
                                return {
                                    "status": "success",
                                    "message": f"Подключение к HTX Spot успешно (через {url}). Статус: {data.get('status', 'OK')}",
                                    "server_time": "N/A"
                                }
                except:
                    continue
            
            return {
                "status": "error",
                "message": "Не удалось подключиться к HTX Spot (возможно, изменился API)"
            }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к HTX Spot: {str(e)}"
            }
    
    async def check_mexc_spot(self) -> Dict[str, any]:
        """Проверка подключения к MEXC Spot"""
        try:
            # Попробуем несколько URL для MEXC
            urls = [
                "https://www.mexc.com/api/platform/spot/market/v2/currencies",
                "https://www.mexc.com/api/platform/spot/market/v2/ticker",
                "https://www.mexc.com/api/platform/spot/market/v2/pairs"
            ]
            
            for url in urls:
                try:
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("code") == 200 or "data" in data:
                                return {
                                    "status": "success",
                                    "message": f"Подключение к MEXC Spot успешно (через {url}). Статус: {data.get('code', 'OK')}",
                                    "server_time": "N/A"
                                }
                except:
                    continue
            
            return {
                "status": "error",
                "message": "Не удалось подключиться к MEXC Spot (возможно, изменился API)"
            }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка подключения к MEXC Spot: {str(e)}"
            }
    
    async def check_all_exchanges(self):
        """Проверка всех поддерживаемых бирж"""
        print("🔍 Финальная проверка подключения ко всем биржам...")
        print("=" * 70)
        
        # Список всех проверок
        checks = [
            ("Bybit Perpetual", self.check_bybit_perpetual),
            ("KuCoin Perpetual", self.check_kucoin_perpetual),
            ("Binance Spot", self.check_binance_spot),
            ("OKX Spot", self.check_okx_spot),
            ("Kraken Spot", self.check_kraken_spot),
            ("Gate.io Spot", self.check_gate_io_spot),
            ("HTX Spot", self.check_htx_spot),
            ("MEXC Spot", self.check_mexc_spot),
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
        print("\n" + "=" * 70)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        
        successful = sum(1 for result in results.values() if result["status"] == "success")
        total = len(results)
        
        print(f"✅ Успешно подключено: {successful}/{total}")
        print(f"❌ Ошибки подключения: {total - successful}/{total}")
        
        if successful == total:
            print("\n🎉 Все биржи подключены успешно!")
        else:
            print(f"\n⚠️  {total - successful} бирж(и) не удалось подключить.")
        
        print("\n📋 Рекомендации по устранению проблем:")
        print("1. Для Bybit: Требуется специальная настройка заголовков")
        print("2. Для Binance: Используйте VPN или прокси (географическая блокировка)")
        print("3. Для Kraken: Установите библиотеку Brotli: pip install Brotli")
        print("4. Для HTX/MEXC: Возможно, изменился API - проверьте документацию")
        
        print("\n🔧 Для полной проверки с API ключами используйте:")
        print("python3 check_exchange_connections.py")
        
        return results


async def main():
    """Основная функция"""
    async with FinalExchangeChecker() as checker:
        await checker.check_all_exchanges()


if __name__ == "__main__":
    asyncio.run(main())