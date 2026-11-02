from typing import List


class LocalVectorizer:
    """Embedding provider injected into Glia (Glia never imports one itself).

    Exposes embed() for a single query and embed_many() for batches, as the Glia spec requires.
    Runs locally with fastembed, so no extra API key is needed.
    """

    def __init__(self, model_name: str, dims: int):
        from fastembed import TextEmbedding  # imported here so the model only loads when needed

        self.dims = dims
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, text: str) -> List[float]:
        return next(iter(self._model.embed([text]))).tolist()

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        return [v.tolist() for v in self._model.embed(list(texts))]
