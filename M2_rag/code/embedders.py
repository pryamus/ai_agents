"""Эмбеддеры: TF-IDF (офлайн, sklearn) и MiniLM (BERT, sentence-transformers).

Оба реализуют один интерфейс ``fit() + encode()`` и возвращают
L2-нормированные векторы float32 — тогда косинусное сходство = скалярное
произведение, и поиск — это матрично-векторное умножение.

* :class:`TfidfEmbedder` — «словарный» метод: вес слова = редкость в корпусе.
  Ничего не скачивает, не понимает синонимы («деплой» ≠ «развёртывание»).
  Идеален для офлайн-демо и как fallback.
* :class:`MiniLMEmbedder` — BERT-семантика: модель отдаёт вектор смысла,
  синонимы и переводы близки в векторном пространстве. Порт (~470 МБ)
  скачивается с HuggingFace один раз и кэшируется.

Переключение: переменная окружения RAG_EMBEDDER = auto | tfidf | minilm,
RAG_MODEL — имя модели HuggingFace (по умолчанию мультиязычный MiniLM).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
import numpy as np

DEFAULT_MINILM_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EmbedderError(RuntimeError):
    """Эмбеддер недоступен (нет пакета, нет сети, не скачалась модель)."""


class Embedder(ABC):
    """Единый контракт: fit по корпусу (если нужен) + encode в нормированные векторы."""

    name: str = "abstract"

    @property
    @abstractmethod
    def dim(self) -> int:
        """Размерность вектора (для TF-IDF известна после fit)."""

    def fit(self, texts: list[str]) -> None:
        """Подготовиться по корпусу. Для BERT — no-op."""

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Вернуть матрицу (len(texts), dim) float32, строки L2-нормированы."""

    # Персистентность состояния: у TF-IDF оно обученное (векторайзер),
    # у BERT — ничего (веса неизменны, их качает sentence-transformers).
    def save_state(self, directory: Path) -> None:
        """Сохранить обучённое состояние эмбеддера в каталог индекса."""

    def load_state(self, directory: Path) -> None:
        """Восстановить обучённое состояние (вызывается после name-проверки)."""


class TfidfEmbedder(Embedder):
    """TF-IDF (1-2 граммы) с ограничением словаря."""

    name = "tfidf"

    def __init__(self, max_features: int = 30_000, ngram_range: tuple[int, int] = (1, 2)) -> None:
        self._vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            lowercase=True,
        )
        self._dim = 0
        self._fitted = False

    @property
    def dim(self) -> int:
        return self._dim

    def fit(self, texts: list[str]) -> None:

        if not texts:
            self._dim, self._fitted = 0, False
            return
        matrix = self._vectorizer.fit_transform(texts)
        self._dim = matrix.shape[1]
        self._fitted = True

    def encode(self, texts: list[str]) -> np.ndarray:


        if not self._fitted:
            raise EmbedderError("TF-IDF не обучен: сначала fit() по корпусу")
        matrix = self._vectorizer.transform(texts)          # слова вне словаря игнорируются
        matrix = normalize(matrix, norm="l2", axis=1)
        return np.asarray(matrix.todense(), dtype=np.float32)

    def save_state(self, directory: Path) -> None:
        if not self._fitted:
            return
        import joblib

        joblib.dump(self._vectorizer, directory / "tfidf_vectorizer.joblib")

    def load_state(self, directory: Path) -> None:
        path = directory / "tfidf_vectorizer.joblib"
        if not path.exists():
            return
        import joblib

        self._vectorizer = joblib.load(path)
        self._fitted = True
        self._dim = len(self._vectorizer.vocabulary_)


class MiniLMEmbedder(Embedder):
    """BERT-эмбеддинги через sentence-transformers (ленивая загрузка модели)."""

    name = "minilm"

    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbedderError(
                "sentence-transformers не установлен: pip install sentence-transformers"
            ) from exc
        self._model_name = model_name or os.environ.get("RAG_MODEL") or DEFAULT_MINILM_MODEL
        try:
            self._model = SentenceTransformer(self._model_name, device=device)
        except Exception as exc:  # нет сети / нет диска / битый кэш
            raise EmbedderError(f"не удалось загрузить модель {self._model_name!r}: {exc}") from exc
        # sentence-transformers переименовал метод в get_embedding_dimension;
        # поддерживаем обе версии пакета
        getter = getattr(self._model, "get_embedding_dimension", None)
        if getter is None:
            getter = self._model.get_sentence_embedding_dimension
        self._dim = int(getter())

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,   # L2-норм: косинус = dot product
            convert_to_numpy=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


def make_embedder(kind: str | None = None) -> Embedder:
    """Собрать эмбеддер по строке kind / переменной окружения RAG_EMBEDDER.

    ``auto`` (по умолчанию): пробуем MiniLM, при любой ошибке — TF-IDF.
    Благодаря fallback практика работает даже без интернета и HuggingFace.
    """
    kind = (kind or os.environ.get("RAG_EMBEDDER", "auto")).lower()
    if kind == "tfidf":
        return TfidfEmbedder()
    if kind == "minilm":
        return MiniLMEmbedder()
    if kind != "auto":
        raise EmbedderError(f"неизвестный эмбеддер: {kind!r} (ожидается auto|tfidf|minilm)")
    try:
        return MiniLMEmbedder()
    except EmbedderError as exc:
        print(f"[chunker->fallback] MiniLM недоступен: {exc}\n[chunker->fallback] используем TF-IDF")
        return TfidfEmbedder()
