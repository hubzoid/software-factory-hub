# Contributing (synthetic sample)

- Python 3.10 or later, standard library only at runtime.
- Run the tests with `python -m pytest -q` before every commit.
- Money is handled with `decimal.Decimal` and rounded once, at the end, to two places with ROUND_HALF_UP.
- Keep functions small and typed. One test file per module under `tests/`.
