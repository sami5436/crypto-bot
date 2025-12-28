#!/usr/bin/env python3
"""
Parse and summarize backtest scan results.
Reads logs/backtest_scan_results.txt and generates a summary.
"""

import re
from collections import defaultdict

INPUT_FILE = "logs/backtest_scan_results.txt"
OUTPUT_FILE = "logs/backtest_summary.txt"


def parse_results(filepath):
    """Parse the backtest results file."""
    results = []
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Split by period
    periods = re.split(r'-{40,}\nPERIOD:', content)
    
    for period_block in periods[1:]:  # Skip header
        # Extract period name
        period_match = re.search(r'^([^\(]+)\(([^\)]+)\)', period_block)
        if not period_match:
            continue
        
        period_name = period_match.group(1).strip()
        date_range = period_match.group(2).strip()
        
        # Extract winner and return
        winner_match = re.search(r'WINNER:\s+([A-Z_\s]+)\n=+\nReturn:\s+([+-]?\d+\.\d+)%', period_block)
        if winner_match:
            winner = winner_match.group(1).strip()
            return_pct = float(winner_match.group(2))
        else:
            winner = "UNKNOWN"
            return_pct = 0.0
        
        # Extract all strategy results
        strategy_results = {}
        for strategy in ['Mean Reversion', 'Trend Following', 'Voting']:
            pattern = rf'{strategy}\s+([+-]?\d+\.\d+)%\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)%\s+\$\s*([\d\.]+)'
            match = re.search(pattern, period_block)
            if match:
                strategy_results[strategy] = {
                    'return': float(match.group(1)),
                    'trips': int(match.group(2)),
                    'long': int(match.group(3)),
                    'short': int(match.group(4)),
                    'win_rate': float(match.group(5)),
                    'final': float(match.group(6))
                }
        
        results.append({
            'period': period_name,
            'dates': date_range,
            'winner': winner,
            'return': return_pct,
            'strategies': strategy_results
        })
    
    return results


def generate_summary(results):
    """Generate summary statistics."""
    lines = []
    lines.append("=" * 70)
    lines.append("BACKTEST SCAN SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    
    # Count wins by strategy
    wins = defaultdict(int)
    returns_by_strategy = defaultdict(list)
    
    for r in results:
        wins[r['winner']] += 1
        for strategy, data in r['strategies'].items():
            returns_by_strategy[strategy].append(data['return'])
    
    lines.append("WINNER COUNTS:")
    lines.append("-" * 40)
    for strategy, count in sorted(wins.items(), key=lambda x: -x[1]):
        pct = count / len(results) * 100
        lines.append(f"  {strategy:<20} {count:>3} wins ({pct:.1f}%)")
    lines.append("")
    
    # Separate results by timeframe type
    monthly_data = [r for r in results if not r['period'].startswith('Q') and 'H' not in r['period'] and 'Full' not in r['period']]
    quarterly_data = [r for r in results if r['period'].startswith('Q')]
    
    # helper to print stats table
    def print_stats_table(title, dataset):
        if not dataset: return
        lines.append(title)
        lines.append("-" * 60)
        lines.append(f"{'Strategy':<20} {'Avg Return':<12} {'Win Rate':<10} {'Best':<10}")
        lines.append("-" * 60)
        
        # Calculate stats per strategy for this dataset
        strat_returns = defaultdict(list)
        for r in dataset:
            for s, d in r['strategies'].items():
                strat_returns[s].append(d['return'])
        
        for strategy in ['Mean Reversion', 'Trend Following', 'Voting']:
            rets = strat_returns.get(strategy, [])
            if rets:
                avg = sum(rets) / len(rets)
                positive = sum(1 for x in rets if x > 0)
                win_rate = (positive / len(rets)) * 100
                best = max(rets)
                lines.append(f"{strategy:<20} {avg:>+9.2f}%   {win_rate:>5.1f}%    {best:>+9.2f}%")
        lines.append("")

    # 1. Monthly Stats
    print_stats_table("MONTHLY PERFORMANCE (Avg per Month)", monthly_data)
    
    # 2. Quarterly Stats
    print_stats_table("QUARTERLY PERFORMANCE (Avg per Quarter)", quarterly_data)

    # Best and worst periods
    sorted_results = sorted(results, key=lambda x: x['return'], reverse=True)
    
    lines.append("TOP 5 BEST PERIODS:")
    lines.append("-" * 40)
    for r in sorted_results[:5]:
        lines.append(f"  {r['period']:<15} {r['return']:>+7.2f}% ({r['winner']})")
    lines.append("")
    
    lines.append("TOP 5 WORST PERIODS:")
    lines.append("-" * 40)
    for r in sorted_results[-5:]:
        lines.append(f"  {r['period']:<15} {r['return']:>+7.2f}% ({r['winner']})")
    lines.append("")
    
    # Monthly breakdown table
    lines.append("FULL RESULTS TABLE:")
    lines.append("-" * 70)
    lines.append(f"{'Period':<15} {'Winner':<18} {'Return':>10} {'Long':>6} {'Short':>6}")
    lines.append("-" * 70)
    
    for r in results:
        winner_data = r['strategies'].get(r['winner'].replace('_', ' ').title(), {})
        longs = winner_data.get('long', 0)
        shorts = winner_data.get('short', 0)
        lines.append(f"{r['period']:<15} {r['winner']:<18} {r['return']:>+9.2f}% {longs:>6} {shorts:>6}")
    
    lines.append("")
    lines.append("=" * 70)
    lines.append("KEY INSIGHTS:")
    lines.append("=" * 70)
    
    # Calculate insights based on Monthly data only for accuracy
    total_months = len(monthly_data)
    if total_months > 0:
        profitable_months = sum(1 for r in monthly_data if r['return'] > 0)
        avg_monthly_return = sum(r['return'] for r in monthly_data) / total_months
        
        # Best monthly strategy
        m_strat_rets = defaultdict(list)
        for r in monthly_data:
             for s, d in r['strategies'].items():
                m_strat_rets[s].append(d['return'])
        
        best_monthly_strat = max(m_strat_rets.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else -999)
        
        lines.append(f"1. Profitable Months: {profitable_months}/{total_months} ({profitable_months/total_months*100:.1f}%)")
        lines.append(f"2. Avg Winner Return: {avg_monthly_return:.2f}% (Monthly)")
        lines.append(f"3. Consistency King:  {best_monthly_strat[0]} (Avg Monthly: {sum(best_monthly_strat[1])/len(best_monthly_strat[1]):.2f}%)")
    
    # Monthly and Quarterly patterns
    for year in ['2024', '2025']:
        # Monthly stats
        m_results = [r for r in monthly_data if f'_{year}' in r['period']]
        if m_results:
            best_month = max(m_results, key=lambda x: x['return'])
            worst_month = min(m_results, key=lambda x: x['return'])
            lines.append(f"4. Best Month {year}:   {best_month['period']:<10} ({best_month['return']:>+7.2f}%)")
            lines.append(f"5. Worst Month {year}:  {worst_month['period']:<10} ({worst_month['return']:>+7.2f}%)")
            
        # Quarterly stats
        q_results = [r for r in quarterly_data if f'_{year}' in r['period']]
        if q_results:
            best_q = max(q_results, key=lambda x: x['return'])
            lines.append(f"6. Best Quarter {year}: {best_q['period']:<10} ({best_q['return']:>+7.2f}%)")
    
    lines.append("")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def main():
    print("Parsing backtest results...")
    results = parse_results(INPUT_FILE)
    print(f"Found {len(results)} periods")
    
    summary = generate_summary(results)
    
    # Print to console
    print("\n" + summary)
    
    # Save to file
    with open(OUTPUT_FILE, 'w') as f:
        f.write(summary)
    
    print(f"\nSummary saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
