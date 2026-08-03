"""Renderer registries: doc key → renderer class.

Two registries, one per snapshot kind. A new solution document = one new module
in renderers/docs/ plus an entry in `DOC_RENDERERS` (and in
`constants.ALL_DOC_KEYS`); a new transcript document = the same, against
`TRANSCRIPT_DOC_RENDERERS` and `constants.ALL_TRANSCRIPT_DOC_KEYS`.
"""

from __future__ import annotations

from docgen.renderers.base import DocRenderer, TranscriptDocRenderer
from docgen.renderers.docs.actions import ActionsRenderer
from docgen.renderers.docs.data_dictionary import DataDictionaryRenderer
from docgen.renderers.docs.deployment import DeploymentRenderer
from docgen.renderers.docs.design_data_dictionary import DataDictionaryDesignRenderer
from docgen.renderers.docs.design_deployment import DeploymentDesignRenderer
from docgen.renderers.docs.design_hld import HldDesignRenderer
from docgen.renderers.docs.design_hygiene import HygieneDesignRenderer
from docgen.renderers.docs.design_integration import IntegrationDesignRenderer
from docgen.renderers.docs.design_licensing import LicensingDesignRenderer
from docgen.renderers.docs.design_lld import LldDesignRenderer
from docgen.renderers.docs.design_security import SecurityDesignRenderer
from docgen.renderers.docs.discovery_rraid import DiscoveryRraidRenderer
from docgen.renderers.docs.hygiene import HygieneRenderer
from docgen.renderers.docs.licensing import LicensingRenderer
from docgen.renderers.docs.hld import HldRenderer
from docgen.renderers.docs.integration import IntegrationRenderer
from docgen.renderers.docs.lld import LldRenderer
from docgen.renderers.docs.meeting_notes import MeetingNotesRenderer
from docgen.renderers.docs.requirements import RequirementsRenderer
from docgen.renderers.docs.rraid import RraidRenderer
from docgen.renderers.docs.security_model import SecurityModelRenderer

DOC_RENDERERS: dict[str, type[DocRenderer]] = {
    LldRenderer.key: LldRenderer,
    DataDictionaryRenderer.key: DataDictionaryRenderer,
    SecurityModelRenderer.key: SecurityModelRenderer,
    DeploymentRenderer.key: DeploymentRenderer,
    LicensingRenderer.key: LicensingRenderer,
    HygieneRenderer.key: HygieneRenderer,
    HldRenderer.key: HldRenderer,
    IntegrationRenderer.key: IntegrationRenderer,
    RraidRenderer.key: RraidRenderer,
}

# The transcript registry deliberately reuses the solution document keys. The
# same key produces the *design intent* version before build and the *as-built*
# version afterwards — one document with two points in its life, one Word
# template, and a meaningful comparison between the two.
TRANSCRIPT_DOC_RENDERERS: dict[str, type[TranscriptDocRenderer]] = {
    # session record — no solution counterpart
    MeetingNotesRenderer.key: MeetingNotesRenderer,
    RequirementsRenderer.key: RequirementsRenderer,
    ActionsRenderer.key: ActionsRenderer,
    # design intent — same keys as the solution document set
    HldDesignRenderer.key: HldDesignRenderer,
    LldDesignRenderer.key: LldDesignRenderer,
    DataDictionaryDesignRenderer.key: DataDictionaryDesignRenderer,
    SecurityDesignRenderer.key: SecurityDesignRenderer,
    DeploymentDesignRenderer.key: DeploymentDesignRenderer,
    LicensingDesignRenderer.key: LicensingDesignRenderer,
    IntegrationDesignRenderer.key: IntegrationDesignRenderer,
    DiscoveryRraidRenderer.key: DiscoveryRraidRenderer,
    HygieneDesignRenderer.key: HygieneDesignRenderer,
}


def get_renderer(key: str) -> DocRenderer | None:
    cls = DOC_RENDERERS.get(key)
    return cls() if cls else None


def get_transcript_renderer(key: str) -> TranscriptDocRenderer | None:
    cls = TRANSCRIPT_DOC_RENDERERS.get(key)
    return cls() if cls else None
