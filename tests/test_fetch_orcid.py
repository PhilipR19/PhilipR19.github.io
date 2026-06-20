from scripts.fetch_orcid import format_citation, bold_author

def test_format_citation_minimal():
    csl = {
        "author": [{"family": "Ruppert", "given": "Philip"},
                    {"family": "Kersten", "given": "Sander"}],
        "title": "A test paper on adipose epigenetics",
        "container-title": "Journal of Lipid Research",
        "issued": {"date-parts": [[2026]]},
        "DOI": "10.1000/test",
    }
    out = format_citation(csl)
    assert "Ruppert" in out
    assert "*A test paper on adipose epigenetics*" in out
    assert "Journal of Lipid Research" in out
    assert "2026" in out
    assert "https://doi.org/10.1000/test" in out

def test_bold_author_marks_ruppert():
    assert bold_author("Philip Ruppert") == "**Philip Ruppert**"
    assert bold_author("Sander Kersten") == "Sander Kersten"
