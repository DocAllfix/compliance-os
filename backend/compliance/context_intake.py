from __future__ import annotations

from compliance.schemas import CompanyContext


def build_context_prompt_block(ctx: CompanyContext) -> str:
    """
    Produces a plain-text block injected into the system prompt for Phase 1
    (evidence extraction) and Phase 3 (gap analysis).

    Example output:
        Company context: Hartley Construction Ltd operates in Construction
        with 51–250 employees. Currently not certified against ISO standards.
        Operating across 2–5 sites.
        Standards under assessment: ISO 9001:2015, ISO 45001:2018.
    """
    certified_map = {
        "yes":         "currently certified",
        "no":          "not yet certified",
        "in_progress": "working towards certification",
    }
    # Sprint R0 — defensive normalisation: older frontends sent display labels
    # ("No", "In progress") instead of canonical values, which fell through the
    # map and produced broken prompt English ("Currently No against ISO
    # standards"). Normalise case/spacing before the lookup.
    certified_key = (ctx.certified or "").strip().lower().replace(" ", "_")
    certified_str = certified_map.get(certified_key, ctx.certified)

    # Normalise en-dash variants ("11–50") to plain hyphens for the prompt.
    employee_range = (ctx.employee_range or "").replace("–", "-")
    sites_count = (ctx.sites_count or "").replace("–", "-")

    sites_str = (
        f"{sites_count} site"
        if sites_count == "1"
        else f"{sites_count} sites"
    )

    norms_str = ", ".join(ctx.norms) if ctx.norms else "no specific standards selected"

    # Piano motore Fase 2 (JURISDICTION_FILTER): il paese decide gli obblighi nazionali.
    from compliance import features
    country_str = ""
    if features.on("JURISDICTION_FILTER"):
        from compliance.jurisdiction import context_line
        country_str = "\n" + context_line(getattr(ctx, "country", None))

    return (
        f"Company context: {ctx.company_name} operates in {ctx.sector} "
        f"with {employee_range} employees. "
        f"Currently {certified_str} against ISO standards. "
        f"Operating across {sites_str}.\n"
        f"Standards under assessment: {norms_str}."
        f"{country_str}"
    )
