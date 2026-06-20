from scripts.fetch_publications import format_citation, bold_author, dedupe


def test_format_citation_openalex():
    work = {
        "display_name": "A test paper on adipose epigenetics",
        "publication_year": 2026,
        "doi": "https://doi.org/10.1000/test",
        "authorships": [
            {"author": {"display_name": "Philip M. M. Ruppert"}},
            {"author": {"display_name": "Sander Kersten"}},
        ],
        "primary_location": {"source": {"display_name": "Journal of Lipid Research", "type": "journal"}},
    }
    out = format_citation(work)
    assert "**Philip M. M. Ruppert**" in out
    assert "Sander Kersten" in out and "**Sander Kersten**" not in out
    assert "*A test paper on adipose epigenetics*" in out
    assert "Journal of Lipid Research" in out
    assert "2026" in out
    assert "https://doi.org/10.1000/test" in out


def test_bold_author_marks_ruppert():
    assert bold_author("Philip Ruppert") == "**Philip Ruppert**"
    assert bold_author("Sander Kersten") == "Sander Kersten"


def test_dedupe_keeps_published_and_preprint():
    preprint = {
        "display_name": "Same Paper, Two Versions",
        "publication_year": 2025,
        "type": "preprint",
        "primary_location": {"version": "submittedVersion",
                             "source": {"type": "repository", "display_name": "bioRxiv"}},
    }
    published = {
        "display_name": "Same Paper, Two Versions",
        "publication_year": 2026,
        "type": "article",
        "primary_location": {"version": "publishedVersion",
                             "source": {"type": "journal", "display_name": "eLife"}},
    }
    reps = dedupe([preprint, published])
    years = sorted(r["publication_year"] for r in reps)
    assert years == [2025, 2026]  # both the preprint and the published version are kept
    assert "preprint" in format_citation(preprint)  # preprint is labelled


def test_dedupe_drops_peer_review():
    reps = dedupe([
        {"display_name": "Author response: Some Paper", "type": "peer-review",
         "primary_location": {"source": {"type": "journal"}}},
    ])
    assert reps == []


def test_dedupe_merges_reworded_preprint():
    from scripts.fetch_publications import dedupe
    biorxiv = {
        "display_name": "Acyl-CoA Binding Protein in White and Brown Adipose Tissue is Dispensable for Systemic Energy Metabolism",
        "publication_year": 2025, "type": "preprint",
        "primary_location": {"version": "submittedVersion", "source": {"type": "repository", "display_name": "bioRxiv"}},
    }
    ssrn = {
        "display_name": "Acyl-CoA Binding Protein is Dispensable for White and Brown Adipose Tissue Function",
        "publication_year": 2025, "type": "preprint",
        "primary_location": {"version": "submittedVersion", "source": {"type": "repository", "display_name": "SSRN Electronic Journal"}},
    }
    distinct = {
        "display_name": "Fasting induces ANGPTL4 and reduces LPL activity in human adipose tissue",
        "publication_year": 2020, "type": "article",
        "primary_location": {"version": "publishedVersion", "source": {"type": "journal", "display_name": "Molecular Metabolism"}},
    }
    reps = dedupe([biorxiv, ssrn, distinct])
    titles = sorted(r["display_name"][:20] for r in reps)
    assert len(reps) == 2, titles  # the two Acyl-CoA preprints merge; the ANGPTL4 paper stays
