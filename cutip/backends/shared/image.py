"""Image-reference helpers shared by all backends."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cutip.models.cards.image import ImageCard


def image_alias(card: "ImageCard") -> str:
    """Canonical local tag for an image card: ``<name>:<tag>``.

    This is the tag that backends write after a pull or build so that
    ``create_container`` can always reference the image by card name,
    regardless of the registry path stored in ``card.spec.image``.

    Example: card name ``hello``, tag ``3.20``  →  ``hello:3.20``
    """
    return f"{card.metadata.name}:{card.spec.tag}"


def image_ref(card: "ImageCard") -> str:
    """Full registry reference: ``<image>:<tag>``.

    Example: ``docker.io/library/alpine:3.20``
    """
    return f"{card.spec.image}:{card.spec.tag}"
