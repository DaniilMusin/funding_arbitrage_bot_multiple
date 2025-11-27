"""
Data export functionality for Hummingbot analytics.

Provides capabilities to export trading data, funding P&L, and performance metrics
to various formats including Parquet, CSV, and JSON for offline analysis.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import pandas as pd
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from hummingbot.core.data_storage.database import db_manager, convert_db_to_decimal


class DataExporter:
    """Handles data export operations for analytics and reporting."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._s3_client: Optional[boto3.client] = None

    def _init_s3_client(self, aws_access_key: str, aws_secret_key: str,
                       region: str = "us-east-1") -> None:
        """Initialize S3 client for cloud storage."""
        try:
            self._s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=region
            )
            self.logger.info("S3 client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize S3 client: {e}")
            raise

    async def export_trades_data(self, start_date: datetime, end_date: datetime,
                               strategy: Optional[str] = None,
                               format: str = "parquet") -> Path:
        """Export trades data for specified period."""
        self.logger.info(f"Exporting trades data from {start_date} to {end_date}")

        # Build query
        where_clause = "WHERE executed_at >= ? AND executed_at <= ?"
        params = [start_date, end_date]

        if strategy:
            where_clause += " AND strategy = ?"
            params.append(strategy)

        sql = f"""
        SELECT
            id, exchange, trading_pair, side, amount, price, fee, fee_currency,
            order_id, strategy, executed_at, created_at
        FROM trades
        {where_clause}
        ORDER BY executed_at DESC
        """

        rows = await db_manager.fetch(sql, *params)

        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=[
            'id', 'exchange', 'trading_pair', 'side', 'amount', 'price',
            'fee', 'fee_currency', 'order_id', 'strategy', 'executed_at', 'created_at'
        ])

        # Convert Decimal columns
        decimal_columns = ['amount', 'price', 'fee']
        for col in decimal_columns:
            if col in df.columns:
                df[col] = df[col].apply(convert_db_to_decimal)

        # Add calculated columns
        df['trade_value'] = df['amount'] * df['price']
        df['net_value'] = df.apply(
            lambda row: row['trade_value'] - (row['fee'] or 0), axis=1
        )

        # Export to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trades_export_{timestamp}.{format}"
        output_path = Path("exports") / filename
        output_path.parent.mkdir(exist_ok=True)

        if format == "parquet":
            df.to_parquet(output_path, index=False)
        elif format == "csv":
            df.to_csv(output_path, index=False)
        elif format == "json":
            df.to_json(output_path, orient="records", date_format="iso")
        else:
            raise ValueError(f"Unsupported format: {format}")

        self.logger.info(f"Exported {len(df)} trades to {output_path}")
        return output_path

    async def export_funding_pnl_analysis(self, start_date: datetime, end_date: datetime,
                                        format: str = "parquet") -> Path:
        """Export funding P&L analysis with detailed breakdown."""
        self.logger.info(f"Exporting funding P&L analysis from {start_date} to {end_date}")

        # Complex query for funding analysis
        sql = """
        WITH funding_periods AS (
            SELECT
                exchange,
                trading_pair,
                funding_rate,
                funding_time,
                LAG(funding_time) OVER (
                    PARTITION BY exchange, trading_pair
                    ORDER BY funding_time
                ) as prev_funding_time
            FROM funding_rates
            WHERE funding_time >= ? AND funding_time <= ?
        ),
        position_snapshots AS (
            SELECT
                exchange,
                trading_pair,
                amount,
                entry_price,
                mark_price,
                snapshot_time,
                ROW_NUMBER() OVER (
                    PARTITION BY exchange, trading_pair, DATE(snapshot_time)
                    ORDER BY snapshot_time DESC
                ) as rn
            FROM positions
            WHERE snapshot_time >= ? AND snapshot_time <= ?
        ),
        daily_positions AS (
            SELECT * FROM position_snapshots WHERE rn = 1
        )
        SELECT
            fp.exchange,
            fp.trading_pair,
            fp.funding_time,
            fp.funding_rate,
            dp.amount as position_size,
            dp.mark_price,
            fp.funding_rate * dp.amount * dp.mark_price as estimated_funding_pnl,
            CASE WHEN dp.amount > 0 THEN 'LONG' ELSE 'SHORT' END as position_side
        FROM funding_periods fp
        LEFT JOIN daily_positions dp ON
            fp.exchange = dp.exchange AND
            fp.trading_pair = dp.trading_pair AND
            DATE(fp.funding_time) = DATE(dp.snapshot_time)
        WHERE fp.prev_funding_time IS NOT NULL
        ORDER BY fp.trading_pair, fp.funding_time
        """

        params = [start_date, end_date, start_date, end_date]
        rows = await db_manager.fetch(sql, *params)

        df = pd.DataFrame(rows, columns=[
            'exchange', 'trading_pair', 'funding_time', 'funding_rate',
            'position_size', 'mark_price', 'estimated_funding_pnl', 'position_side'
        ])

        # Convert Decimal columns
        decimal_columns = ['funding_rate', 'position_size', 'mark_price', 'estimated_funding_pnl']
        for col in decimal_columns:
            if col in df.columns:
                df[col] = df[col].apply(convert_db_to_decimal)

        # Add aggregated metrics
        summary_df = df.groupby(['exchange', 'trading_pair']).agg({
            'estimated_funding_pnl': ['sum', 'mean', 'std', 'count'],
            'funding_rate': ['mean', 'min', 'max'],
            'position_size': 'mean'
        }).round(8)

        # Export detailed data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        detail_filename = f"funding_pnl_detail_{timestamp}.{format}"
        summary_filename = f"funding_pnl_summary_{timestamp}.{format}"

        detail_path = Path("exports") / detail_filename
        summary_path = Path("exports") / summary_filename
        detail_path.parent.mkdir(exist_ok=True)

        if format == "parquet":
            df.to_parquet(detail_path, index=False)
            summary_df.to_parquet(summary_path)
        elif format == "csv":
            df.to_csv(detail_path, index=False)
            summary_df.to_csv(summary_path)
        elif format == "json":
            df.to_json(detail_path, orient="records", date_format="iso")
            summary_df.to_json(summary_path, orient="index", date_format="iso")

        self.logger.info(f"Exported funding P&L analysis: {detail_path}, {summary_path}")
        return detail_path

    async def export_hedge_performance(self, start_date: datetime, end_date: datetime,
                                     strategy: str, format: str = "parquet") -> Path:
        """Export hedge operation performance metrics."""
        self.logger.info(f"Exporting hedge performance for {strategy}")

        sql = """
        SELECT
            id, operation_type, total_exposure, target_exposure, hedge_amount,
            hedge_side, hedge_price, slippage, exchange, trading_pair,
            execution_time_ms, status, error_message, executed_at
        FROM hedge_operations
        WHERE strategy = ? AND executed_at >= ? AND executed_at <= ?
        ORDER BY executed_at DESC
        """

        rows = await db_manager.fetch(sql, strategy, start_date, end_date)

        df = pd.DataFrame(rows, columns=[
            'id', 'operation_type', 'total_exposure', 'target_exposure', 'hedge_amount',
            'hedge_side', 'hedge_price', 'slippage', 'exchange', 'trading_pair',
            'execution_time_ms', 'status', 'error_message', 'executed_at'
        ])

        # Convert Decimal columns
        decimal_columns = ['total_exposure', 'target_exposure', 'hedge_amount', 'hedge_price', 'slippage']
        for col in decimal_columns:
            if col in df.columns:
                df[col] = df[col].apply(convert_db_to_decimal)

        # Add performance metrics
        if not df.empty:
            df['hedge_efficiency'] = abs(df['hedge_amount']) / df['total_exposure']
            df['execution_cost_bps'] = (df['slippage'] * 10000).round(2)
            df['success_rate'] = (df['status'] == 'COMPLETED').astype(int)

        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hedge_performance_{strategy}_{timestamp}.{format}"
        output_path = Path("exports") / filename
        output_path.parent.mkdir(exist_ok=True)

        if format == "parquet":
            df.to_parquet(output_path, index=False)
        elif format == "csv":
            df.to_csv(output_path, index=False)
        elif format == "json":
            df.to_json(output_path, orient="records", date_format="iso")

        self.logger.info(f"Exported hedge performance: {output_path}")
        return output_path

    async def export_risk_metrics(self, start_date: datetime, end_date: datetime,
                                strategy: Optional[str] = None, format: str = "parquet") -> Path:
        """Export risk metrics and portfolio analytics."""
        self.logger.info(f"Exporting risk metrics from {start_date} to {end_date}")

        where_clause = "WHERE calculated_at >= ? AND calculated_at <= ?"
        params = [start_date, end_date]

        if strategy:
            where_clause += " AND strategy = ?"
            params.append(strategy)

        sql = f"""
        SELECT
            strategy, total_exposure_usd, max_drawdown, var_95, var_99,
            sharpe_ratio, sortino_ratio, max_leverage, concentration_risk,
            calculated_at, period_start, period_end
        FROM risk_metrics
        {where_clause}
        ORDER BY calculated_at DESC
        """

        rows = await db_manager.fetch(sql, *params)

        df = pd.DataFrame(rows, columns=[
            'strategy', 'total_exposure_usd', 'max_drawdown', 'var_95', 'var_99',
            'sharpe_ratio', 'sortino_ratio', 'max_leverage', 'concentration_risk',
            'calculated_at', 'period_start', 'period_end'
        ])

        # Convert Decimal columns
        decimal_columns = [
            'total_exposure_usd', 'max_drawdown', 'var_95', 'var_99',
            'sharpe_ratio', 'sortino_ratio', 'max_leverage', 'concentration_risk'
        ]
        for col in decimal_columns:
            if col in df.columns:
                df[col] = df[col].apply(convert_db_to_decimal)

        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"risk_metrics_{timestamp}.{format}"
        output_path = Path("exports") / filename
        output_path.parent.mkdir(exist_ok=True)

        if format == "parquet":
            df.to_parquet(output_path, index=False)
        elif format == "csv":
            df.to_csv(output_path, index=False)
        elif format == "json":
            df.to_json(output_path, orient="records", date_format="iso")

        self.logger.info(f"Exported risk metrics: {output_path}")
        return output_path

    async def upload_to_s3(self, file_path: Path, bucket: str, prefix: str = "",
                          aws_access_key: str = "", aws_secret_key: str = "") -> str:
        """Upload exported file to S3."""
        if not self._s3_client and aws_access_key:
            self._init_s3_client(aws_access_key, aws_secret_key)

        if not self._s3_client:
            raise ValueError("S3 client not initialized")

        try:
            s3_key = f"{prefix}/{file_path.name}" if prefix else file_path.name

            self._s3_client.upload_file(str(file_path), bucket, s3_key)
            s3_url = f"s3://{bucket}/{s3_key}"

            self.logger.info(f"Uploaded {file_path} to {s3_url}")
            return s3_url

        except ClientError as e:
            self.logger.error(f"Failed to upload to S3: {e}")
            raise

    async def scheduled_export(self, export_config: Dict[str, Any]) -> None:
        """Run scheduled data export based on configuration."""
        self.logger.info("Running scheduled data export")

        try:
            # Calculate date range
            end_date = datetime.now(timezone.utc)
            start_date = end_date - pd.Timedelta(days=export_config.get("days", 7))

            export_tasks = []

            # Export trades if configured
            if export_config.get("export_trades", True):
                task = self.export_trades_data(
                    start_date, end_date,
                    strategy=export_config.get("strategy"),
                    format=export_config.get("format", "parquet")
                )
                export_tasks.append(("trades", task))

            # Export funding P&L if configured
            if export_config.get("export_funding", True):
                task = self.export_funding_pnl_analysis(
                    start_date, end_date,
                    format=export_config.get("format", "parquet")
                )
                export_tasks.append(("funding", task))

            # Export hedge performance if configured
            if export_config.get("export_hedge") and export_config.get("strategy"):
                task = self.export_hedge_performance(
                    start_date, end_date,
                    strategy=export_config["strategy"],
                    format=export_config.get("format", "parquet")
                )
                export_tasks.append(("hedge", task))

            # Export risk metrics if configured
            if export_config.get("export_risk", True):
                task = self.export_risk_metrics(
                    start_date, end_date,
                    strategy=export_config.get("strategy"),
                    format=export_config.get("format", "parquet")
                )
                export_tasks.append(("risk", task))

            # Run exports concurrently
            results = {}
            for export_type, task in export_tasks:
                try:
                    file_path = await task
                    results[export_type] = file_path

                    # Upload to S3 if configured
                    if export_config.get("upload_to_s3") and export_config.get("s3_bucket"):
                        await self.upload_to_s3(
                            file_path,
                            export_config["s3_bucket"],
                            prefix=export_config.get("s3_prefix", "hummingbot-exports"),
                            aws_access_key=export_config.get("aws_access_key", ""),
                            aws_secret_key=export_config.get("aws_secret_key", "")
                        )

                except Exception as e:
                    self.logger.error(f"Failed to export {export_type}: {e}")

            self.logger.info(f"Scheduled export completed. Exported: {list(results.keys())}")
            return results

        except Exception as e:
            self.logger.error(f"Scheduled export failed: {e}")
            raise


# Global data exporter instance
data_exporter = DataExporter()


# Utility functions
async def export_data_for_analysis(days: int = 7, strategy: Optional[str] = None) -> Dict[str, Path]:
    """Quick export function for analysis."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - pd.Timedelta(days=days)

    results = {}

    # Export trades
    results["trades"] = await data_exporter.export_trades_data(start_date, end_date, strategy)

    # Export funding P&L
    results["funding"] = await data_exporter.export_funding_pnl_analysis(start_date, end_date)

    # Export risk metrics
    results["risk"] = await data_exporter.export_risk_metrics(start_date, end_date, strategy)

    return results