"""Explicit synthetic seed into the dedicated demo ledger only."""
from app.infrastructure.database import engine_for
from app.workflows.posting import Store
from scripts.seed_demo import seed

if __name__ == '__main__':
    engine=engine_for()
    if engine.url.database!='kcd_demo':raise RuntimeError('Synthetic seed requires kcd_demo; other ledgers preserved')
    try:seed(Store(engine))
    finally:engine.dispose()
    print('Synthetic demo records ready.')
