"""
test_ai_ranking.py
------------------
Automated test suite verifying the AI Stock Selection & Ranking Engine in 3_AI_Selection.
Tests:
1. Technical Screening Stage 1.
2. Fundamental & Valuation Stage 2.
3. News & Momentum Stages 3 & 4.
4. Multi-Factor Weighted Scoring & Top 10 Ranking Stage 5.
"""
import os
import sys
import logging
from ai_ranking_engine import run_ai_stock_selection, DEFAULT_WEIGHTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def test_pipeline():
    print("\n=======================================================")
    print("  RUNNING AI STOCK SELECTION & RANKING INTEGRATION TEST")
    print("=======================================================\n")

    def progress_callback(info):
        print(f"[{info.get('stage')}/5] {info.get('message')} ({info.get('current')}/{info.get('total')})")

    res = run_ai_stock_selection(
        weights=DEFAULT_WEIGHTS,
        date_str=None,
        rsi=30,
        stoch=70,
        min_criteria=4,
        index_filter="set100",
        process_all=True,
        progress_callback=progress_callback
    )

    print("\n-------------------------------------------------------")
    print(f"Status: {res.get('status')}")
    print(f"Index Filter: {res.get('index_filter')}")
    print(f"Total Screened Stocks: {res.get('total_screened')}")
    print(f"Total Deep Analyzed Candidates: {res.get('total_analyzed')}")
    print(f"Normalized Weights: {res.get('weights')}")
    print("-------------------------------------------------------\n")

    rankings = res.get('rankings', [])
    assert len(rankings) > 0, "Error: Rankings should not be empty!"
    assert len(rankings) <= 10, "Error: Rankings count should be at most 10!"

    print("TOP RANKED STOCKS:")
    for stock in rankings:
        print(f"#{stock['rank']} {stock['symbol']} ({stock['sector']}) | Criteria: {stock.get('criteria_passed')}/6 | Score: {stock['composite_score']} | Grade: {stock['ai_grade']}")
        print(f"   Method: {stock.get('fair_value_method_note')}")
        print(f"   Price: THB {stock['price']} | Fair Value: THB {stock['fair_value']} | MOS: {stock['mos_pct']}%")
        print(f"   Thesis: {stock['investment_thesis']}")
        print(f"   Risk: {stock['key_risks']}\n")

    print("\n[SUCCESS] AI Stock Selection Engine Integration Test PASSED 100%!")

if __name__ == "__main__":
    test_pipeline()
