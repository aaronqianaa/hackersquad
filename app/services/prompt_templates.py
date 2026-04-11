import json
from dataclasses import dataclass


ARTIFACT_TYPES = (
    "hero",
    "product_description",
    "ads",
    "email",
    "social",
    "page_draft",
    "creative_brief",
)


@dataclass(frozen=True)
class PromptTemplate:
    artifact_type: str
    version: str
    instructions: str

    def render(self, brand_pattern: dict, product_context: dict, instruction: str | None = None) -> str:
        prompt = (
            f"{self.instructions}\n"
            "Brand pattern:\n"
            f"{json.dumps(brand_pattern, indent=2, sort_keys=True)}\n"
            "Product context:\n"
            f"{json.dumps(product_context, indent=2, sort_keys=True)}\n"
            "Keep claims realistic, use a clear CTA when relevant, and avoid unsupported promises."
        )
        if instruction:
            prompt = f"{prompt}\nRevision instruction:\n{instruction.strip()}"
        return prompt


PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    "hero": PromptTemplate(
        artifact_type="hero",
        version="hero.v1",
        instructions=(
            "Write a landing-page hero section. Return exactly three lines labeled "
            "Headline:, Subheadline:, CTA:. Keep the headline under 12 words."
        ),
    ),
    "product_description": PromptTemplate(
        artifact_type="product_description",
        version="product_description.v1",
        instructions=(
            "Write a 2-3 sentence product description focused on benefits, premium feel, "
            "and concrete use-case clarity."
        ),
    ),
    "ads": PromptTemplate(
        artifact_type="ads",
        version="ads.v1",
        instructions=(
            "Write three distinct paid-ad variants. Return exactly three lines labeled "
            "Ad 1:, Ad 2:, Ad 3:."
        ),
    ),
    "email": PromptTemplate(
        artifact_type="email",
        version="email.v1",
        instructions=(
            "Write a short marketing email. Return exactly two sections labeled "
            "Subject: and Body:."
        ),
    ),
    "social": PromptTemplate(
        artifact_type="social",
        version="social.v1",
        instructions=(
            "Write one concise organic social post with a hook, one benefit, and a CTA."
        ),
    ),
    "page_draft": PromptTemplate(
        artifact_type="page_draft",
        version="page_draft.v1",
        instructions=(
            "Write a concise page-outline draft covering hero, benefits, proof, offer, FAQ, and CTA."
        ),
    ),
    "creative_brief": PromptTemplate(
        artifact_type="creative_brief",
        version="creative_brief.v1",
        instructions=(
            "Write a concise creative brief covering visual direction, tone, audience angles, "
            "and CTA emphasis."
        ),
    ),
}


def build_prompt(artifact_type: str, brand_pattern: dict, product_context: dict, instruction: str | None = None) -> str:
    template = PROMPT_TEMPLATES.get(artifact_type)
    if not template:
        raise ValueError(f"Unsupported artifact type: {artifact_type}")
    return template.render(brand_pattern, product_context, instruction=instruction)


def prompt_version_for(artifact_type: str) -> str:
    template = PROMPT_TEMPLATES.get(artifact_type)
    if not template:
        raise ValueError(f"Unsupported artifact type: {artifact_type}")
    return template.version
