# arxiv-to-code

Autonomous pipeline that scans arXiv daily, finds papers with no existing implementations, scores them for buildability, and generates builder tasks to implement them.

## How It Works

```
arXiv API → Scanner → Impl Checker → Scorer → Builder → Publisher
                          ↓                      ↓          ↓
                     GitHub API            State Machine   GitHub + Twitter
                   PapersWithCode
```

1. **Scanner** fetches recent papers from arXiv (cs.AI, cs.CR, cs.LG, cs.SE)
2. **Impl Checker** searches GitHub and PapersWithCode for existing implementations
3. **Scorer** scores papers (0-100) based on:
   - No existing implementation (+40)
   - Security domain (+20)
   - Algorithm/pseudocode in abstract (+15)
   - Freshness < 48h (+15)
   - Code already available (-30)
4. **Builder** generates task prompts for papers scoring ≥60
5. **Publisher** generates tweet threads and dev.to drafts for shipped implementations

## Installation

```bash
git clone https://github.com/clawinfra/arxiv-to-code.git
cd arxiv-to-code
pip install -e ".[dev]"
```

## Usage

### Run the pipeline

```bash
python -m arxiv_to_code.pipeline --hours 48 --max-results 100
```

### Dry run (no state changes)

```bash
python -m arxiv_to_code.pipeline --dry-run
```

### Custom state directory

```bash
python -m arxiv_to_code.pipeline --state-dir /path/to/state
```

## Project Structure

```
arxiv_to_code/
  scanner.py       — Fetch papers from arXiv API
  scorer.py        — Score papers for buildability + novelty + impact
  impl_checker.py  — Check GitHub + PapersWithCode for existing impls
  builder.py       — Generate builder task prompts
  publisher.py     — Generate tweet threads + dev.to drafts
  pipeline.py      — Orchestrate the full loop
  state.py         — State management (processed, queue, published)
state/
  processed.json   — Papers already seen
  queue.json       — Scored papers pending build
  published.json   — Shipped repos with metrics
tests/
  test_scanner.py
  test_scorer.py
  test_impl_checker.py
  test_pipeline.py
```

## Scoring Heuristics

| Factor | Points | Description |
|--------|--------|-------------|
| No existing impl | +40 | Paper has no GitHub/PWC implementation |
| Security domain | +20 | Paper is in cs.CR or cs.CY |
| Algorithm indicators | +15 | Abstract mentions algorithm/pseudocode |
| Freshness (< 48h) | +15 | First-mover advantage |
| Code available | -30 | Abstract mentions released code |

**Build threshold: 60 points**

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=arxiv_to_code

# Run specific test file
pytest tests/test_scorer.py -v
```

## License

MIT
