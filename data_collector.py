#!/usr/bin/env python3
"""
Historical Crypto Data Collector
Downloads OHLCV data from CryptoCompare (free API, works worldwide).
Can fetch hourly candles for 365+ days!
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import time

# =============================================================================
# CONFIGURATION
# =============================================================================

# Coins to download (CryptoCompare uses simple symbols)
COINS = {
    'BTC': 'btc_usd',
    'ETH': 'eth_usd',
}

# Output directory
OUTPUT_DIR = 'historical_data'

# CryptoCompare API (free tier - 100k calls/month)
API_BASE = 'https://min-api.cryptocompare.com/data/v2'


# =============================================================================
# DATA COLLECTOR (CryptoCompare)
# =============================================================================

def download_hourly(symbol: str, days: int = 365) -> pd.DataFrame:
    """
    Download hourly OHLCV data from CryptoCompare.
    CryptoCompare allows 2000 hourly candles per request!
    
    Args:
        symbol: Coin symbol (e.g., 'BTC', 'ETH')
        days: Number of days of data to fetch
    
    Returns:
        DataFrame with OHLCV data
    """
    print(f"📥 Downloading {symbol}/USD (hourly) - last {days} days...")
    
    try:
        all_candles = []
        hours_needed = days * 24
        hours_per_request = 2000  # CryptoCompare max
        
        # Start from now and work backwards
        to_ts = int(datetime.now().timestamp())
        
        batch = 0
        while hours_needed > 0:
            batch += 1
            limit = min(hours_per_request, hours_needed)
            
            print(f"   📦 Fetching batch {batch} ({limit} candles)...", end='\r')
            
            url = f"{API_BASE}/histohour"
            params = {
                'fsym': symbol,
                'tsym': 'USD',
                'limit': limit,
                'toTs': to_ts
            }
            
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('Response') != 'Success':
                print(f"   [WARN] API error: {data.get('Message', 'Unknown error')}")
                break
            
            candles = data.get('Data', {}).get('Data', [])
            if not candles:
                break
            
            all_candles = candles + all_candles  # Prepend (we're going backwards)
            
            # Move further back in time
            to_ts = candles[0]['time'] - 1
            hours_needed -= len(candles)
            
            time.sleep(0.5)  # Rate limiting
        
        if not all_candles:
            print(f"   [WARN] No data returned for {symbol}")
            return pd.DataFrame()
        
        # Build DataFrame
        df = pd.DataFrame(all_candles)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={
            'open': 'open',
            'high': 'high', 
            'low': 'low',
            'close': 'close',
            'volumefrom': 'volume'
        })
        
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        # Remove any zero-price candles (sometimes API returns empty candles)
        df = df[df['close'] > 0]
        
        date_from = df['timestamp'].iloc[0]
        date_to = df['timestamp'].iloc[-1]
        
        print(f"    Got {len(df):,} candles from {date_from.date()} to {date_to.date()}")
        return df
        
    except Exception as e:
        print(f"    Error: {e}")
        return pd.DataFrame()


def download_daily(symbol: str, days: int = 365) -> pd.DataFrame:
    """Download daily OHLCV data from CryptoCompare."""
    print(f"📥 Downloading {symbol}/USD (daily) - last {days} days...")
    
    try:
        url = f"{API_BASE}/histoday"
        params = {
            'fsym': symbol,
            'tsym': 'USD',
            'limit': days
        }
        
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        
        if data.get('Response') != 'Success':
            print(f"   [WARN] API error: {data.get('Message', 'Unknown error')}")
            return pd.DataFrame()
        
        candles = data.get('Data', {}).get('Data', [])
        if not candles:
            return pd.DataFrame()
        
        df = pd.DataFrame(candles)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={'volumefrom': 'volume'})
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df = df[df['close'] > 0]  # Remove empty candles
        
        print(f"    Got {len(df)} candles from {df['timestamp'].iloc[0].date()} to {df['timestamp'].iloc[-1].date()}")
        return df
        
    except Exception as e:
        print(f"    Error: {e}")
        return pd.DataFrame()


def save_to_csv(df: pd.DataFrame, filename: str) -> str:
    """Save DataFrame to CSV file."""
    if df.empty:
        return ""
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.csv")
    df.to_csv(filepath, index=False)
    print(f"   💾 Saved to {filepath}")
    
    return filepath


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "=" * 60)
    print(" CRYPTO DATA COLLECTOR (CryptoCompare)")
    print("=" * 60)
    print(f"Coins: {', '.join(COINS.keys())}")
    print(f"Timeframes: hourly, daily")
    print(f"Output: {OUTPUT_DIR}/")
    print("=" * 60 + "\n")
    
    all_files = []
    
    for symbol, filename_prefix in COINS.items():
        print(f"\n{'─' * 50}")
        print(f" {symbol}/USD")
        print(f"{'─' * 50}")
        
        # Download hourly data (365 days = ~8,760 candles!)
        df_hourly = download_hourly(symbol, days=730)
        if not df_hourly.empty:
            filepath = save_to_csv(df_hourly, f"{filename_prefix}_hourly")
            all_files.append(filepath)
        
        time.sleep(1)
        
        # Download daily data
        df_daily = download_daily(symbol, days=730)
        if not df_daily.empty:
            filepath = save_to_csv(df_daily, f"{filename_prefix}_daily")
            all_files.append(filepath)
        
        time.sleep(1)
    
    # Summary
    print("\n" + "=" * 60)
    print(" DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"Files created: {len(all_files)}")
    for f in all_files:
        size = os.path.getsize(f) / 1024
        lines = sum(1 for _ in open(f)) - 1
        print(f"   • {f} ({size:.1f} KB, {lines:,} candles)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
