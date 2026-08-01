"""Renderer registry: doc key → renderer class. A new document = one new module
in renderers/docs/ plus one entry here (and in constants.ALL_DOC_KEYS)."""

from __future__ import annotations

from docgen.renderers.base import DocRenderer
from docgen.renderers.docs.data_dictionary import DataDictionaryRenderer
from docgen.renderers.docs.deployment import DeploymentRenderer
from docgen.renderers.docs.hygiene import HygieneRenderer
from docgen.renderers.docs.licensing import LicensingRenderer
from docgen.renderers.docs.lld import LldRenderer
from docgen.renderers.docs.security_model import SecurityModelRenderer

DOC_RENDERERS: dict[str, type[DocRenderer]] = {
    LldRenderer.key: LldRenderer,
    DataDictionaryRenderer.key: DataDictionaryRenderer,
    SecurityModelRenderer.key: SecurityModelRenderer,
    DeploymentRenderer.key: DeploymentRenderer,
    LicensingRenderer.key: LicensingRenderer,
    HygieneRenderer.key: HygieneRenderer,
}


def get_renderer(key: str) -> DocRenderer | None:
    cls = DOC_RENDERERS.get(key)
    return cls() if cls else None
