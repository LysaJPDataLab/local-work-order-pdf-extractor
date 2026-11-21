import json
import tempfile
import unittest
from pathlib import Path

import fitz

from src.work_order_extractor import (
    PageText,
    _is_wo_start,
    extract_pdf,
    parse_record,
    run_local,
    split_os_pages,
)


def sample_text(language: str = "en", number: str = "700000001") -> str:
    """Small synthetic form. No customer, supplier, site or asset data is used."""
    labels = {
        "en": {
            "number": "WO Number", "kind": "Type of work", "type": "PLANNED CORRECTIVE",
            "done": "Work Done", "alarms": "ALARMS", "other": "OTHER DATA",
            "failure": "FAILURE MODES", "stops": "MACHINE STOP", "labor": "LABOR",
            "materials": "MATERIALS", "tools": "TOOLS", "client": "Client:",
            "site": "Site:", "asset": "Equipment:", "date": "Date:", "reason": "Reason for Work:",
        },
        "es": {
            "number": "Nº OT", "kind": "Clase de Trabajo", "type": "CORRECTIVO PLANIFICADO",
            "done": "Trabajo realizado", "alarms": "ALARMAS", "other": "OTROS DATOS",
            "failure": "MODOS DE FALLO", "stops": "PARADA MÁQUINA", "labor": "MANO DE OBRA",
            "materials": "MATERIALES", "tools": "HERRAMIENTAS", "client": "Cliente:",
            "site": "Centro:", "asset": "Equipo:", "date": "Fecha:", "reason": "Motivo de trabajo:",
        },
        "pt": {
            "number": "Nº OS", "kind": "Tipo de trabalho", "type": "CORRETIVO PLANEJADO",
            "done": "Trabalho realizado", "alarms": "ALARMES", "other": "OUTROS DADOS",
            "failure": "MODOS DE FALHA", "stops": "PARADA DA MÁQUINA", "labor": "MÃO DE OBRA",
            "materials": "MATERIAIS", "tools": "FERRAMENTAS", "client": "Cliente:",
            "site": "Unidade:", "asset": "Equipamento:", "date": "Data:", "reason": "Motivo do trabalho:",
        },
    }[language]
    return f"""{labels['number']}
{labels['kind']}
{number}
{labels['type']}
{labels['client']}
Example Customer
{labels['site']}
Example Site
{labels['asset']}
Equipment Model / ASSET-001
{labels['date']}
15.04.2026
{labels['reason']}
Routine inspection
{labels['done']}
Synthetic maintenance activity for parser testing.
{labels['alarms']}
Alarm code
Description
ALM-12345
Synthetic alarm description
{labels['other']}
Line hours
Equipment hours
Energy
100.00
200.00
300.00
{labels['failure']}
System
Subsystem
Component
Failure mode
DRIVE
MOTOR
SENSOR
SIGNAL ERROR
{labels['stops']}
Stop Date Stop Time Start Date Start Time Stopped Time
15.04.2026 07:00 15.04.2026 09:30 2.50
{labels['labor']}
Technician
Example Technician
{labels['materials']}
Part
Synthetic spare part
{labels['tools']}
Tool
Synthetic torque wrench
"""


class ParserTests(unittest.TestCase):
    def test_headers_are_recognized_in_english_spanish_and_portuguese(self):
        for language in ("en", "es", "pt"):
            with self.subTest(language=language):
                self.assertTrue(_is_wo_start(sample_text(language)))

    def test_continuation_page_stays_with_previous_work_order(self):
        pages = [
            PageText(1, sample_text("en", "700000001")),
            PageText(2, "LABOR\nSynthetic continuation row\n"),
            PageText(3, sample_text("es", "700000002")),
        ]
        grouped = split_os_pages(pages)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0]["source_pages"], [1, 2])
        self.assertEqual(grouped[1]["source_pages"], [3])

    def test_extracts_fields_and_child_sections_from_english_form(self):
        record = parse_record({"raw_text": sample_text("en"), "source_pages": [1]})
        self.assertEqual(record["wo_number"], "700000001")
        self.assertEqual(record["maintenance_type"], "PLANNED CORRECTIVE")
        self.assertEqual(record["other_data"]["line_hours"], 100.0)
        self.assertEqual(record["machine_stops"][0]["stopped_time_hours"], 2.5)
        self.assertEqual(record["alarms"][0]["code"], "ALM-12345")
        self.assertEqual(record["source_pages"], [1])
        self.assertTrue(record["labor"])
        self.assertTrue(record["materials"])
        self.assertTrue(record["tools"])

    def test_portuguese_labels_ignore_accents_for_matching(self):
        record = parse_record({"raw_text": sample_text("pt"), "source_pages": [1]})
        self.assertEqual(record["wo_number"], "700000001")
        self.assertIn("pt", record["detected_structural_languages"])
        self.assertTrue(record["recognized_sections"]["work_done"])
        self.assertTrue(record["recognized_sections"]["machine_stops"])

    def test_mixed_structural_languages_are_reported_without_translating_values(self):
        text = sample_text("en").replace("Work Done", "Trabajo realizado").replace("MATERIALS", "MATERIALES")
        record = parse_record({"raw_text": text, "source_pages": [1]})
        self.assertIn("en", record["detected_structural_languages"])
        self.assertIn("es", record["detected_structural_languages"])
        self.assertIn("Synthetic maintenance activity", record["work_done"])

    def test_negative_stop_duration_is_preserved_and_flagged(self):
        text = sample_text("es").replace("2.50", "-2.50")
        record = parse_record({"raw_text": text, "source_pages": [1]})
        self.assertEqual(record["machine_stops"][0]["stopped_time_hours"], -2.5)
        self.assertIn("negative_stop_duration_present_in_source", record["quality_flags"])

    def test_unrecognized_header_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "unrecognized_layout.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((40, 50), "Synthetic document without a work-order header")
            document.save(pdf_path)
            document.close()
            with self.assertRaisesRegex(ValueError, "Nenhuma OS foi identificada"):
                extract_pdf(pdf_path)


class LocalProcessingTests(unittest.TestCase):
    def test_pdf_extraction_and_incremental_processing_are_local(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            pdf_path = input_dir / "synthetic_work_order.pdf"

            document = fitz.open()
            page = document.new_page()
            page.insert_textbox(fitz.Rect(40, 40, 550, 780), sample_text("en"), fontsize=8)
            document.save(pdf_path)
            document.close()

            extracted = extract_pdf(pdf_path)
            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0]["wo_number"], "700000001")

            run_local(input_dir, output_dir)
            output_path = output_dir / "ordens_servico.json"
            first_output = output_path.read_text(encoding="utf-8")
            data = json.loads(first_output)
            self.assertEqual(len(data), 1)
            self.assertNotIn("source_path", data[0])
            self.assertNotIn("source_sha256", data[0])
            self.assertNotIn(str(input_dir.resolve()), first_output)

            run_local(input_dir, output_dir)
            second_output = output_path.read_text(encoding="utf-8")
            self.assertEqual(first_output, second_output)

            state = json.loads((output_dir / "controle_processamento.json").read_text(encoding="utf-8"))
            self.assertIn("synthetic_work_order.pdf", state["files"])
            self.assertNotIn(str(input_dir.resolve()), json.dumps(state))


if __name__ == "__main__":
    unittest.main()
