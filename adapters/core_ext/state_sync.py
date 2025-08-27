import asyncio
import os
from typing import Sequence

import asyncpg

from hummingbot.client.hummingbot_application import HummingbotApplication


async def sync_loop():
    """Continuously sync open positions into a Postgres table."""
    dsn = os.environ.get("STATE_SYNC_DSN", "postgresql://localhost/postgres")
    conn = await asyncpg.connect(dsn)
    insert_sql = (
        "INSERT INTO active_positions("
        "id, controller_id, connector_name, trading_pair, side, timestamp, "
        "volume_traded_quote, amount, breakeven_price, unrealized_pnl_quote, "
        "cum_fees_quote) "
        "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)"
    )
    try:
        while True:
            app = HummingbotApplication.main_application()
            positions: Sequence = []
            if app is not None and app.markets_recorder is not None:
                positions = app.markets_recorder.get_all_positions()
            async with conn.transaction():
                await conn.execute("DELETE FROM active_positions")
                for pos in positions:
                    side = pos.side.value if hasattr(pos.side, "value") else pos.side
                    await conn.execute(
                        insert_sql,
                        pos.id,
                        pos.controller_id,
                        pos.connector_name,
                        pos.trading_pair,
                        side,
                        pos.timestamp,
                        pos.volume_traded_quote,
                        pos.amount,
                        pos.breakeven_price,
                        pos.unrealized_pnl_quote,
                        pos.cum_fees_quote,
                    )
            await asyncio.sleep(1)
    finally:
        await conn.close()
