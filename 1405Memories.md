# Session notes — 14 May 2026

## Fixes applied this session

### 1. `.claude/settings.local.json` — merge conflict resolved
File had unresolved git merge conflict markers (lines 24–31). Fixed by keeping both sides:
- Kept: `python -c "from src.universes..."`, `npm run *`, `wait`, `python3 -m json.tool`
- Kept: `python -c ' *)`
File is now valid JSON. `/doctor` should be clean.

### 2. `CLAUDE.md` — corrected and updated
Several inaccuracies fixed:

| Item | Was | Now |
|------|-----|-----|
| Strategy count | 7 | 18 (11 PineScript-derived added) |
| Frontend source path | `app/frontend/src/` (implied) | `app/frontend/` directly — no `src/` subdir |
| Widget types | 13 types | 18 types (added `shannon-entropy`, `correlation-matrix`, `transfer-entropy`, `fundamental`, `hurst-exponent`) |
| Hooks directory | not mentioned | `hooks/useQueries.ts` etc. — widgets fetch through here, not `lib/api.ts` directly |
| Charts | recharts only | recharts + `lightweight-charts` (TradingView OHLCV in HistoricalPriceWidget) |
| `src/data/providers.py` | missing | added to directory tree |
| Single test command | missing | `poetry run pytest src/path/to/test.py -v` |

New strategies added to STRATEGY_MAP (PineScript-derived):
`PivotPointSupertrendStrategy`, `LaguerreRSIStrategy`, `HurstChoppinessStrategy`,
`MansfieldMinerviniStrategy`, `WVFConnorsRSIStrategy`, `ChandelierExitStrategy`,
`BankerFundFlowStrategy`, `CPRCamarillaStrategy`, `PositionCostDistributionStrategy`,
`SETSwingDashboardStrategy` (+ `VADERStrategy` was missing from original list too)
