"""Import reviewed private JSON into the configured shop DB. Never creates stock."""
import json
import sys
from pathlib import Path
from app.infrastructure import database as db
from app.modules.purchasing.reviews import import_review

if __name__ == '__main__':
    engine=db.engine_for()
    if not engine.url.database.startswith('kcd_shop'):
        raise RuntimeError('Choose the private shop database; do not mix real bills with demo data')
    records=json.loads(Path(sys.argv[1]).read_text())
    for record in records:
        saved=import_review(engine,record['id'],record['payload'],'partner-confirmed-import')
        print('Order review saved:',saved['id'],'Stock unchanged')
    engine.dispose()
