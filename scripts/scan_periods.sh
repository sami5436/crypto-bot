#!/bin/bash
# Futures Backtest Scanner - Tests different time periods with leverage 3
# Output saved to logs/backtest_scan_results.txt

OUTPUT_FILE="logs/backtest_scan_results.txt"
LEVERAGE=3

echo "========================================"
echo "FUTURES BACKTEST SCANNER"
echo "Leverage: ${LEVERAGE}x"
echo "Started: $(date)"
echo "========================================"

# Clear previous results
echo "FUTURES BACKTEST SCAN RESULTS" > $OUTPUT_FILE
echo "Generated: $(date)" >> $OUTPUT_FILE
echo "Leverage: ${LEVERAGE}x" >> $OUTPUT_FILE
echo "Mode: REALISTIC" >> $OUTPUT_FILE
echo "========================================" >> $OUTPUT_FILE
echo "" >> $OUTPUT_FILE

# Monthly ranges (2024)
PERIODS=(
    "2024-01-01 2024-01-31 Jan_2024"
    "2024-02-01 2024-02-29 Feb_2024"
    "2024-03-01 2024-03-31 Mar_2024"
    "2024-04-01 2024-04-30 Apr_2024"
    "2024-05-01 2024-05-31 May_2024"
    "2024-06-01 2024-06-30 Jun_2024"
    "2024-07-01 2024-07-31 Jul_2024"
    "2024-08-01 2024-08-31 Aug_2024"
    "2024-09-01 2024-09-30 Sep_2024"
    "2024-10-01 2024-10-31 Oct_2024"
    "2024-11-01 2024-11-30 Nov_2024"
    "2024-12-01 2024-12-31 Dec_2024"
    # Quarter ranges
    "2024-01-01 2024-03-31 Q1_2024"
    "2024-04-01 2024-06-30 Q2_2024"
    "2024-07-01 2024-09-30 Q3_2024"
    "2024-10-01 2024-12-31 Q4_2024"
    # Half year
    "2024-01-01 2024-06-30 H1_2024"
    "2024-07-01 2024-12-31 H2_2024"
    # Full year
    "2024-01-01 2024-12-31 Full_2024"
    # 2025
    "2025-01-01 2025-01-31 Jan_2025"
    "2025-02-01 2025-02-28 Feb_2025"
    "2025-03-01 2025-03-31 Mar_2025"
    "2025-04-01 2025-04-30 Apr_2025"
    "2025-05-01 2025-05-31 May_2025"
    "2025-06-01 2025-06-30 Jun_2025"
    "2025-07-01 2025-07-31 Jul_2025"
    "2025-08-01 2025-08-31 Aug_2025"
    "2025-09-01 2025-09-30 Sep_2025"
    "2025-10-01 2025-10-31 Oct_2025"
    "2025-11-01 2025-11-30 Nov_2025"
    "2025-12-01 2025-12-31 Dec_2025"
    # 2025 Quarters
    "2025-01-01 2025-03-31 Q1_2025"
    "2025-04-01 2025-06-30 Q2_2025"
    "2025-07-01 2025-09-30 Q3_2025"
    "2025-10-01 2025-12-31 Q4_2025"
    # Half year
    "2025-01-01 2025-06-30 H1_2025"
    "2025-07-01 2025-12-31 H2_2025"
    # Full year
    "2025-01-01 2025-12-31 Full_2025"
    # All Time
    "2024-01-01 2025-12-31 All_Available"
)

TOTAL=${#PERIODS[@]}
COUNT=0

for period in "${PERIODS[@]}"; do
    read -r START END LABEL <<< "$period"
    COUNT=$((COUNT + 1))
    
    echo ""
    echo "[$COUNT/$TOTAL] Testing: $LABEL ($START to $END)"
    echo "----------------------------------------" >> $OUTPUT_FILE
    echo "PERIOD: $LABEL ($START to $END)" >> $OUTPUT_FILE
    echo "----------------------------------------" >> $OUTPUT_FILE
    
    # Run the backtest and capture output
    python paper_trader.py 6 --start $START --end $END --leverage $LEVERAGE 2>&1 | tee -a $OUTPUT_FILE
    
    echo "" >> $OUTPUT_FILE
    echo "" >> $OUTPUT_FILE
done

echo ""
echo "========================================"
echo "SCAN COMPLETE"
echo "Results saved to: $OUTPUT_FILE"
echo "========================================"

# Add summary at end
echo "" >> $OUTPUT_FILE
echo "========================================" >> $OUTPUT_FILE
echo "SCAN COMPLETED: $(date)" >> $OUTPUT_FILE
echo "========================================" >> $OUTPUT_FILE
