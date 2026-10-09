DOCUMENTS = {
    "doc-alice": {"owner": "alice", "content": "alpha"},
    "doc-bob": {"owner": "bob", "content": "bravo"},
}


def read_document(actor: str, document_id: str) -> dict:
    document = DOCUMENTS.get(document_id)
    allowed = document is not None and document["owner"] == actor
    return {
        "accepted": document is not None,
        "authorized": allowed,
        "content": document["content"] if allowed else None,
    }


def list_documents(actor: str) -> list[str]:
    return sorted(document_id for document_id, value in DOCUMENTS.items() if value["owner"] == actor)
