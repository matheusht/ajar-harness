DOCUMENTS = {
    "doc-alice": {"owner": "alice", "content": "alpha"},
    "doc-bob": {"owner": "bob", "content": "bravo"},
}


def read_document(actor: str, document_id: str) -> dict:
    document = DOCUMENTS.get(document_id)
    if document is None:
        return {"status": "not_found"}
    return {"status": "ok", "content": document["content"]}


def list_documents(actor: str) -> list[str]:
    return sorted(document_id for document_id, value in DOCUMENTS.items() if value["owner"] == actor)
