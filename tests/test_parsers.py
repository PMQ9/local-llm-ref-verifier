"""Tests for the rule-based citation style parsers."""

from ref_verifier.parsers import PARSERS, detect_style
from ref_verifier.parsers.apa import APAParser
from ref_verifier.parsers.chicago import ChicagoParser
from ref_verifier.parsers.harvard import HarvardParser
from ref_verifier.parsers.ieee import IEEEParser
from ref_verifier.parsers.vancouver import VancouverParser


# --- APA ---

APA_SAMPLES = [
    (
        "Grady, J. S., Her, M., Moreno, G., Perez, C., & Yelinek, J. (2019). "
        "Emotions in storybooks: A comparison of storybooks that represent ethnic "
        "and racial groups in the United States. Psychology of Popular Media Culture, "
        "8(3), 207-217. https://doi.org/10.1037/ppm0000185",
        {
            "title": "Emotions in storybooks: A comparison of storybooks that represent "
            "ethnic and racial groups in the United States",
            "year": 2019,
            "journal": "Psychology of Popular Media Culture",
            "volume": "8",
            "pages": "207-217",
            "doi": "10.1037/ppm0000185",
        },
    ),
    (
        "Smith, J., & Doe, A. (2020). Machine learning in healthcare. "
        "Nature Medicine, 26(3), 309-316.",
        {
            "title": "Machine learning in healthcare",
            "year": 2020,
            "journal": "Nature Medicine",
            "volume": "26",
            "pages": "309-316",
        },
    ),
]


class TestAPAParser:
    parser = APAParser()

    def test_parse_full_apa_reference(self):
        for raw, expected in APA_SAMPLES:
            ref = self.parser.parse_reference(raw, "ref_01")
            assert ref is not None, f"Failed to parse: {raw[:60]}"
            assert ref.title == expected["title"]
            assert ref.year == expected["year"]
            assert ref.journal == expected["journal"]

    def test_score_high_for_apa(self):
        for raw, _ in APA_SAMPLES:
            score = self.parser.score_match(raw)
            assert score > 0.5, f"APA score too low ({score}) for: {raw[:60]}"

    def test_score_low_for_ieee(self):
        ieee_ref = '[1] G. Liu, "TDM networks," IEEE Trans., vol. 46, pp. 695-701, 1997.'
        score = self.parser.score_match(ieee_ref)
        assert score < 0.4


# --- IEEE ---

IEEE_SAMPLES = [
    (
        '[1] G. Liu, K. Y. Lee, and H. F. Jordan, "TDM and TWDM de Bruijn networks '
        'and shufflenets," IEEE Trans. Comp., vol. 46, pp. 695-701, Jun. 1997.',
        {
            "title": "TDM and TWDM de Bruijn networks and shufflenets",
            "year": 1997,
            "journal": "IEEE Trans. Comp.",
            "volume": "46",
            "pages": "695-701",
        },
    ),
    (
        '[2] T. Kaczorek, "Minimum energy control of fractional positive electrical '
        'circuits," Archives of Electrical Engineering, vol. 65, no. 2, pp. 191-201, 2016.',
        {
            "title": "Minimum energy control of fractional positive electrical circuits",
            "year": 2016,
            "volume": "65",
            "pages": "191-201",
        },
    ),
]


class TestIEEEParser:
    parser = IEEEParser()

    def test_parse_full_ieee_reference(self):
        for raw, expected in IEEE_SAMPLES:
            ref = self.parser.parse_reference(raw, "ref_01")
            assert ref is not None, f"Failed to parse: {raw[:60]}"
            assert ref.title == expected["title"]
            assert ref.year == expected["year"]
            assert ref.volume == expected["volume"]

    def test_score_high_for_ieee(self):
        for raw, _ in IEEE_SAMPLES:
            score = self.parser.score_match(raw)
            assert score > 0.5, f"IEEE score too low ({score}) for: {raw[:60]}"

    def test_score_low_for_apa(self):
        apa_ref = (
            "Smith, J. (2020). Machine learning in healthcare. "
            "Nature Medicine, 26(3), 309-316."
        )
        score = self.parser.score_match(apa_ref)
        assert score < 0.4


# --- Vancouver ---

VANCOUVER_SAMPLES = [
    (
        "1. Halpern SD, Ubel PA, Caplan AL. Solid-organ transplantation in "
        "HIV-infected patients. N Engl J Med. 2002 Jul 25;347(4):284-7.",
        {
            "title": "Solid-organ transplantation in HIV-infected patients",
            "year": 2002,
            "journal": "N Engl J Med",
            "volume": "347",
            "pages": "284-7",
        },
    ),
    (
        "Rose ME, Huerbin MB, Melick J, Marion DW, Palmer AM, Schiding JK, et al. "
        "Regulation of interstitial excitatory amino acid concentrations after "
        "cortical contusion injury. Brain Res. 2002;935(1-2):40-6.",
        {
            "title": "Regulation of interstitial excitatory amino acid concentrations "
            "after cortical contusion injury",
            "year": 2002,
            "journal": "Brain Res",
            "volume": "935",
            "pages": "40-6",
        },
    ),
]


class TestVancouverParser:
    parser = VancouverParser()

    def test_parse_full_vancouver_reference(self):
        for raw, expected in VANCOUVER_SAMPLES:
            ref = self.parser.parse_reference(raw, "ref_01")
            assert ref is not None, f"Failed to parse: {raw[:60]}"
            assert ref.title == expected["title"]
            assert ref.year == expected["year"]
            assert ref.volume == expected["volume"]

    def test_score_high_for_vancouver(self):
        for raw, _ in VANCOUVER_SAMPLES:
            score = self.parser.score_match(raw)
            assert score > 0.5, f"Vancouver score too low ({score}) for: {raw[:60]}"


# --- Harvard ---

HARVARD_SAMPLES = [
    (
        "Black, J. and Barnes, J.L. (2015) 'Fiction and social cognition: "
        "The effect of viewing award-winning television dramas on the theory of mind', "
        "Psychology of Aesthetics, Creativity and the Arts, 9(4), pp. 423-429.",
        {
            "title": "Fiction and social cognition: The effect of viewing award-winning "
            "television dramas on the theory of mind",
            "year": 2015,
            "journal": "Psychology of Aesthetics, Creativity and the Arts",
            "pages": "423-429",
        },
    ),
]


class TestHarvardParser:
    parser = HarvardParser()

    def test_parse_full_harvard_reference(self):
        for raw, expected in HARVARD_SAMPLES:
            ref = self.parser.parse_reference(raw, "ref_01")
            assert ref is not None, f"Failed to parse: {raw[:60]}"
            assert ref.title == expected["title"]
            assert ref.year == expected["year"]

    def test_score_high_for_harvard(self):
        for raw, _ in HARVARD_SAMPLES:
            score = self.parser.score_match(raw)
            assert score > 0.5, f"Harvard score too low ({score}) for: {raw[:60]}"


# --- Chicago ---

CHICAGO_SAMPLES = [
    (
        'Kwon, Hyeyoung. "Inclusion Work: Children of Immigrants Claiming '
        'Membership in Everyday Life." American Journal of Sociology 127, '
        "no. 6 (2022): 1818-59. https://doi.org/10.1086/720277.",
        {
            "title": "Inclusion Work: Children of Immigrants Claiming Membership in Everyday Life",
            "year": 2022,
            "journal": "American Journal of Sociology",
            "volume": "127",
            "pages": "1818-59",
            "doi": "10.1086/720277",
        },
    ),
]


class TestChicagoParser:
    parser = ChicagoParser()

    def test_parse_full_chicago_reference(self):
        for raw, expected in CHICAGO_SAMPLES:
            ref = self.parser.parse_reference(raw, "ref_01")
            assert ref is not None, f"Failed to parse: {raw[:60]}"
            assert ref.title == expected["title"]
            assert ref.year == expected["year"]

    def test_score_high_for_chicago(self):
        for raw, _ in CHICAGO_SAMPLES:
            score = self.parser.score_match(raw)
            assert score > 0.5, f"Chicago score too low ({score}) for: {raw[:60]}"


# --- Style detection ---


class TestStyleDetection:
    def test_detect_apa_style(self):
        refs = "\n\n".join(raw for raw, _ in APA_SAMPLES)
        assert detect_style(refs) == "apa"

    def test_detect_ieee_style(self):
        refs = "\n".join(raw for raw, _ in IEEE_SAMPLES)
        assert detect_style(refs) == "ieee"

    def test_detect_vancouver_style(self):
        refs = "\n\n".join(raw for raw, _ in VANCOUVER_SAMPLES)
        assert detect_style(refs) == "vancouver"

    def test_detect_harvard_style(self):
        refs = "\n\n".join(raw for raw, _ in HARVARD_SAMPLES)
        assert detect_style(refs) == "harvard"

    def test_detect_chicago_style(self):
        refs = "\n\n".join(raw for raw, _ in CHICAGO_SAMPLES)
        assert detect_style(refs) == "chicago"


# --- Full section parsing ---


class TestFullSectionParsing:
    def test_parse_ieee_section(self):
        section = (
            '[1] G. Liu, K. Y. Lee, and H. F. Jordan, "TDM and TWDM de Bruijn '
            'networks and shufflenets," IEEE Trans. Comp., vol. 46, pp. 695-701, Jun. 1997.\n'
            '[2] T. Kaczorek, "Minimum energy control of fractional positive electrical '
            'circuits," Archives of Electrical Engineering, vol. 65, no. 2, pp. 191-201, 2016.'
        )
        parser = IEEEParser()
        refs = parser.parse_all(section)
        assert len(refs) == 2
        assert refs[0].id == "ref_01"
        assert refs[1].id == "ref_02"

    def test_parse_apa_section(self):
        section = (
            "Smith, J., & Doe, A. (2020). Machine learning in healthcare. "
            "Nature Medicine, 26(3), 309-316.\n\n"
            "Zhang, W., & Li, H. (2021). Deep learning for NLP. "
            "IEEE Transactions, 32(1), 1-20."
        )
        parser = APAParser()
        refs = parser.parse_all(section)
        assert len(refs) == 2
