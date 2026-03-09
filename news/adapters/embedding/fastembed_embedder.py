from fastembed import TextEmbedding

_model = None


def _get_model():
    global _model

    if _model is None:
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    return _model


def embed_text(text: str) -> list[float]:
    model = _get_model()

    vec = list(model.embed([text]))[0]

    return vec.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()

    vectors = list(model.embed(texts))

    return [v.tolist() for v in vectors]
