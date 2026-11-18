"""
shared stubs for the tests that run ``_main`` without a docx file and without kroki
"""

from rebdhuhn.models import EbdCheckResult, EbdTable, EbdTableMetaData, EbdTableRow, EbdTableSubRow

WITH_TABLE = "E_0003"
WITHOUT_TABLE = "E_9999"
# only part of the document if a test asks for it (see the ``failing_scraping`` fixture)
SCRAPING_FAILS = "E_0060"

TWO_STEP_TABLE = EbdTable(
    metadata=EbdTableMetaData(
        ebd_code="E_0003",
        chapter="7.39 AD: Bestellung der Aggregationsebene",
        section="7.39.1 E_0003_Bestellung der Aggregationsebene RZ prüfen",
        ebd_name="E_0003_Bestellung der Aggregationsebene RZ prüfen",
        role="ÜNB",
    ),
    rows=[
        EbdTableRow(
            step_number="1",
            description="Erfolgt der Eingang der Bestellung fristgerecht?",
            sub_rows=[
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=False, subsequent_step_number=None),
                    result_code="A01",
                    note="Fristüberschreitung",
                ),
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=True, subsequent_step_number="2"),
                    result_code=None,
                    note=None,
                ),
            ],
        ),
        EbdTableRow(
            step_number="2",
            description="Erfolgt die Bestellung zum Monatsersten 00:00 Uhr?",
            sub_rows=[
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=False, subsequent_step_number=None),
                    result_code="A02",
                    note="Gewählter Zeitpunkt nicht zulässig",
                ),
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=True, subsequent_step_number="Ende"),
                    result_code=None,
                    note=None,
                ),
            ],
        ),
    ],
)
