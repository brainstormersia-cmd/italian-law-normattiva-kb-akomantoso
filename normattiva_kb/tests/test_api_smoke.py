from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.api.deps import get_db
from app.db import models


def test_api_smoke(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        doc = models.Document(doc_id="doc1", canonical_doc="dpr:917:1986", doc_type="dpr")
        session.add(doc)
        version = models.DocumentVersion(doc_id="doc1", version_tag="v1", checksum_text="abc")
        session.add(version)
        session.flush()
        node = models.Node(
            node_id="node1",
            doc_id="doc1",
            version_id=version.version_id,
            node_type="articolo",
            label="Art. 1",
            canonical_path="art:1",
            sort_key="art:1",
            text_raw="Testo",
            text_clean="Testo",
            text_hash="hash",
            language="it",
        )
        session.add(node)
        session.commit()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/search", params={"q": "Testo"}).status_code == 200
    app.dependency_overrides.clear()
