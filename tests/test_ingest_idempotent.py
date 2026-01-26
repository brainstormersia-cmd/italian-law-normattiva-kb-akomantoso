import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.db import repo
from app.ingestion.raw_store import raw_file_record


def test_ingest_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    xml_path = tmp_path / "sample.xml"
    xml_path.write_text("<atto></atto>", encoding="utf-8")

    with Session() as session:
        data = raw_file_record(xml_path)
        repo.upsert_raw_file(session, data)
        repo.upsert_raw_file(session, data)
        session.commit()
        count = session.query(models.RawFile).count()
        assert count == 1
