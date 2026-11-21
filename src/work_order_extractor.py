from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import fitz  # PyMuPDF
from dotenv import load_dotenv

LOG = logging.getLogger("work_order_extractor")

# O extrator trabalha com chaves canônicas independentes do idioma do formulário.
# Os aliases abrangem os rótulos observados e variantes comuns EN / ES / PT.
import unicodedata


def normalize_label(value: str) -> str:
    """Normaliza rótulos para comparação, preservando o texto original nos dados."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("º", "o").replace("°", "o")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


HEADER_NUMBER_LABELS = {
    "wo number", "wo no", "work order number", "no ot", "n ot", "no os",
    "numero ot", "numero ordem de trabalho", "numero os", "n ordem",
    "ordem de servico", "numero ordem servico",
}
HEADER_TYPE_LABELS = {
    "type of job", "type of work", "job type", "clase de trabajo",
    "tipo de trabalho", "tipo de servicio", "tipo de manutencao",
}
WO_NUMBER_RE = re.compile(r"(?<!\d)(\d{6,12})(?!\d)")
DATE_RE = r"\d{2}\.\d{2}\.\d{4}"
TIME_RE = r"\d{1,2}:\d{2}(?:\s*[AP]M)?"
STOP_ROW_RE = re.compile(
    rf"({DATE_RE})\s+({TIME_RE})\s+({DATE_RE})\s+({TIME_RE})\s+(-?\d+(?:[.,]\d+)?)",
    re.I,
)
NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")

# category -> language -> aliases. Aliases são deliberadamente explícitos:
# isso evita confundir texto livre com cabeçalhos de seção.
LABELS_BY_LANGUAGE = {
    "header_number": {
        "en": ("WO Number", "WO No.", "Work Order Number"),
        "es": ("Nº OT", "Numero OT"),
        "pt": ("Nº OS", "Numero OS", "Nº Ordem", "Ordem de Serviço"),
    },
    "header_type": {
        "en": ("Type of job", "Type of work", "Job type"),
        "es": ("Clase de Trabajo",),
        "pt": ("Tipo de trabalho", "Tipo de serviço", "Tipo de manutenção"),
    },
    "work_done": {
        "en": ("Work Done",), "es": ("Trabajo realizado",),
        "pt": ("Trabalho realizado", "Serviço realizado"),
    },
    "alarms": {
        "en": ("ALARMS", "ALARM LIST"), "es": ("ALARMAS",), "pt": ("ALARMES",),
    },
    "other_data": {
        "en": ("OTHER DATA", "OTHER DATA / READINGS"),
        "es": ("OTROS DATOS",), "pt": ("OUTROS DADOS", "OUTROS DADOS / LEITURAS"),
    },
    "failure_modes": {
        "en": ("FAILURE MODES",), "es": ("MODOS DE FALLO",),
        "pt": ("MODOS DE FALHA",),
    },
    "machine_stops": {
        "en": ("MACHINE STOP", "MACHINE STOPS", "STOP EVENTS"),
        "es": ("PARADA MAQUINA", "PARADAS DE MAQUINA", "TIEMPOS DE PARADA"),
        "pt": ("PARADA DA MAQUINA", "PARADAS DE MAQUINA", "INDISPONIBILIDADE DA MAQUINA", "PARADA DO AEROGERADOR", "EVENTOS DE PARADA"),
    },
    "labor": {
        "en": ("LABOR", "MANPOWER"), "es": ("MANO DE OBRA",),
        "pt": ("MAO DE OBRA",),
    },
    "materials": {
        "en": ("MATERIALS",), "es": ("MATERIALES",), "pt": ("MATERIAIS",),
    },
    "tools": {
        "en": ("TOOLS",), "es": ("HERRAMIENTAS",), "pt": ("FERRAMENTAS",),
    },
}
SECTION_ALIASES = {
    key: tuple(alias for language_aliases in languages.values() for alias in language_aliases)
    for key, languages in LABELS_BY_LANGUAGE.items()
    if key not in {"header_number", "header_type"}
}
SECTION_LABELS = {normalize_label(x) for values in SECTION_ALIASES.values() for x in values}
HEADER_NUMBER_KEYS = {normalize_label(x) for x in HEADER_NUMBER_LABELS}
HEADER_TYPE_KEYS = {normalize_label(x) for x in HEADER_TYPE_LABELS}

FIELD_ALIASES = {
    "date": ("Date:", "Fecha:", "Data:", "Data da OS:"),
    "client": ("Client:", "Cliente:", "Contratante:"),
    "wind_farm": ("WindFarm:", "Wind Farm:", "Parque:", "Parque eolico:", "Complexo eolico:", "Usina:"),
    "wind_turbine": ("Wind turbine:", "Aerogenerador:", "Aerogerador:"),
    "machine": ("Tower Num:", "Machine:", "Máquina:", "Máquina/", "NºTorre:", "Nº Torre:", "Numero da torre:", "Torre:", "Aerogerador Nº:"),
    "reason": ("Reason for Work:", "Motivo de Salida:", "Motivo da saida:", "Motivo do trabalho:", "Razao da OS:"),
}
FIELD_LABEL_KEYS = {normalize_label(alias) for aliases in FIELD_ALIASES.values() for alias in aliases}
FIELD_ALIAS_GROUP_BY_KEY = {
    normalize_label(alias): field_name
    for field_name, aliases in FIELD_ALIASES.items()
    for alias in aliases
}
MAINTENANCE_TYPES = {
    normalize_label(x): x for x in (
        "NON-PLANNED CORRECTIVE", "PLANNED CORRECTIVE",
        "CORRECTIVO NO PLANIFICADO", "CORRECTIVO PLANIFICADO",
        "CORRETIVO NAO PLANEJADO", "CORRETIVO PLANEJADO",
        "MANUTENCAO CORRETIVA NAO PLANEJADA", "MANUTENCAO CORRETIVA PLANEJADA",
    )
}


@dataclass
class PageText:
    page_number: int
    text: str


def normalize_text(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def _lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_text(text).splitlines()]


def _is_wo_start(text: str) -> bool:
    lines = [normalize_label(x) for x in _lines(text) if x]
    for i, line in enumerate(lines):
        if line in HEADER_NUMBER_KEYS:
            window = lines[i + 1:i + 7]
            if any(x in HEADER_TYPE_KEYS for x in window) and any(WO_NUMBER_RE.fullmatch(x) for x in window):
                return True
    # Variação em que os títulos estão unidos na mesma linha do cabeçalho.
    normalized = normalize_label(text)
    has_number_label = any(x in normalized for x in HEADER_NUMBER_KEYS)
    has_type_label = any(x in normalized for x in HEADER_TYPE_KEYS)
    return has_number_label and has_type_label and bool(WO_NUMBER_RE.search(text))


def split_os_pages(pages: Iterable[PageText]) -> list[dict[str, Any]]:
    """Agrupa a primeira página da OS com todas as páginas de continuação."""
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for page in pages:
        text = normalize_text(page.text)
        if _is_wo_start(text):
            if current is not None:
                records.append(current)
            current = {"source_pages": [], "_page_texts": []}
        if current is not None:
            current["source_pages"].append(page.page_number)
            current["_page_texts"].append(text)
    if current is not None:
        records.append(current)
    for record in records:
        record["raw_text"] = "\n\n".join(record.pop("_page_texts"))
    return records


def _section(text: str, section_key: str, _end: str | None = None) -> str:
    """Extrai todas as ocorrências da seção usando aliases EN/ES/PT."""
    lines = _lines(text)
    wanted = {normalize_label(a) for a in SECTION_ALIASES[section_key]}
    chunks: list[str] = []
    for start, line in enumerate(lines):
        if normalize_label(line) not in wanted:
            continue
        end = next(
            (i for i in range(start + 1, len(lines))
             if normalize_label(lines[i]) in SECTION_LABELS),
            len(lines),
        )
        chunk = "\n".join(lines[start + 1:end]).strip()
        if chunk:
            chunks.append(chunk)
    return "\n".join(chunks).strip()


def _next_value(lines: list[str], labels: tuple[str, ...], limit: int = 0) -> str | None:
    wanted = {normalize_label(x.rstrip(":")) for x in labels}
    for i, line in enumerate(lines):
        normalized = normalize_label(line.rstrip(":"))
        # Aceita label isolado e label seguido de valor na mesma linha.
        if normalized in wanted:
            for value in lines[i + 1:]:
                if not value.strip():
                    continue
                value_key = normalize_label(value.rstrip(":"))
                if value_key in SECTION_LABELS:
                    return None
                if value_key in FIELD_LABEL_KEYS:
                    current_group = next((name for name, aliases in FIELD_ALIASES.items()
                                          if wanted.intersection(normalize_label(x.rstrip(":")) for x in aliases)), None)
                    if FIELD_ALIAS_GROUP_BY_KEY.get(value_key) == current_group:
                        continue
                    return None
                if value.endswith(":"):
                    return None
                return " ".join(value.split()).strip(" :-\t") or None
        for label in wanted:
            if normalized.startswith(label + " "):
                return line[len(line.split(":", 1)[0]) + 1:].strip(" :-\t") or None
    return None


def _detect_structural_languages(text: str) -> list[str]:
    """Idiomas inferidos apenas pelos rótulos estruturais, não pelo texto livre."""
    found: set[str] = set()
    lines = {normalize_label(line) for line in _lines(text) if line.strip()}
    for category, per_language in LABELS_BY_LANGUAGE.items():
        if category == "header_number":
            # A forma Nº OT normalizada é ambígua entre PT/ES; classifica pelo idioma do tipo.
            continue
        if category == "header_type":
            for language, aliases in per_language.items():
                if lines.intersection(normalize_label(x) for x in aliases):
                    found.add(language)
        else:
            for language, aliases in per_language.items():
                if lines.intersection(normalize_label(x) for x in aliases):
                    found.add(language)
    return sorted(found)

def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def _parse_other_data(section: str) -> dict[str, float | None]:
    values = []
    for line in _lines(section):
        if not line or line.casefold() in {"horas línea", "horas linea", "horas turbina", "kwh", "line hours", "turbine hours"}:
            continue
        nums = NUMBER_RE.findall(line)
        if nums:
            values.extend(nums)
    values += [""] * max(0, 3 - len(values))
    return {
        "line_hours": _number(values[0] or None),
        "turbine_hours": _number(values[1] or None),
        "kwh": _number(values[2] or None),
    }


def _parse_failure_modes(section: str) -> dict[str, str | None]:
    ignored = {"system", "subsistema", "subsystem", "sistema", "componente", "component", "tipo de fallo", "failure mode"}
    values = [x for x in _lines(section) if x and x.casefold() not in ignored]
    values = values[:4]
    values += [None] * (4 - len(values))
    return dict(zip(("system", "subsystem", "component", "failure_mode"), values))


def _parse_alarms(section: str) -> list[dict[str, str | None]]:
    lines = [x for x in _lines(section) if x]
    rows = []
    code_re = re.compile(r"^(?=[A-Z0-9_-]{4,24}$)(?=.*\d)[A-Z][A-Z0-9_-]*$|^\d{5,10}$", re.I)
    skip = {"código alarma", "codigo alarma", "descripción", "descripcion", "alarm code", "description"}
    for i, line in enumerate(lines):
        if line.casefold() in skip or not code_re.fullmatch(line):
            continue
        description = next((x for x in lines[i + 1:] if x.casefold() not in skip and not code_re.fullmatch(x)), None)
        rows.append({"code": line, "description": description})
    return rows


def _parse_stops(section: str) -> list[dict[str, Any]]:
    rows = []
    for m in STOP_ROW_RE.finditer(section):
        rows.append({
            "stop_date": m.group(1), "stop_time": m.group(2),
            "start_date": m.group(3), "start_time": m.group(4),
            "stopped_time_hours": _number(m.group(5)),
            "stopped_time_raw": m.group(5),
            "duration_review": "negative_duration" if m.group(5).startswith("-") else None,
        })
    return rows


def _nonempty_lines(section: str) -> list[str]:
    """Preserva linhas de tabela; não presume associação entre células mescladas."""
    return [" ".join(x.split()) for x in _lines(section) if x.strip()]


def _recognized_sections(text: str) -> dict[str, bool]:
    line_keys = {normalize_label(line) for line in _lines(text) if line.strip()}
    return {
        section: bool(line_keys.intersection(normalize_label(alias) for alias in aliases))
        for section, aliases in SECTION_ALIASES.items()
    }


def parse_record(record: dict[str, Any]) -> dict[str, Any]:
    raw = normalize_text(record["raw_text"])
    lines = _lines(raw)
    header_index = next((i for i, line in enumerate(lines) if normalize_label(line) in HEADER_NUMBER_KEYS), None)
    header_lines = lines[header_index + 1:] if header_index is not None else lines
    wo_number = None
    job_type = None
    for position, line in enumerate(header_lines[:14]):
        number_match = WO_NUMBER_RE.search(line)
        if number_match:
            wo_number = number_match.group(1)
            prefix = line[:number_match.start()].strip(" :-\t")
            if prefix:
                job_type = prefix
            else:
                job_type = next((x for x in header_lines[position + 1:] if x and normalize_label(x) not in SECTION_LABELS and normalize_label(x) not in HEADER_TYPE_KEYS), None)
            break
    maintenance_type = next((x for x in lines[:35] if normalize_label(x) in MAINTENANCE_TYPES), None)

    def val(*labels: str) -> str | None:
        return _next_value(lines, tuple(labels))

    date = val(*FIELD_ALIASES["date"])
    client = val(*FIELD_ALIASES["client"])
    wind_farm = val(*FIELD_ALIASES["wind_farm"])
    wind_turbine = val(*FIELD_ALIASES["wind_turbine"])
    machine = val(*FIELD_ALIASES["machine"])
    reason = val(*FIELD_ALIASES["reason"])
    detected_languages = _detect_structural_languages(raw)

    sections = {key: _section(raw, key) for key in SECTION_ALIASES}
    recognized_sections = _recognized_sections(raw)
    work_done = sections["work_done"]
    alarms_raw = sections["alarms"]
    other_raw = sections["other_data"]
    failure_raw = sections["failure_modes"]
    stops_raw = sections["machine_stops"]
    labor_raw = sections["labor"]
    materials_raw = sections["materials"]
    tools_raw = sections["tools"]

    quality_flags = []
    if not wo_number:
        quality_flags.append("missing_wo_number")
    if not machine:
        quality_flags.append("missing_machine")
    if not work_done:
        quality_flags.append("missing_work_done")
    if not any(detected_languages):
        quality_flags.append("unrecognized_structural_language_or_layout")
    for section_name, is_present in recognized_sections.items():
        if not is_present:
            quality_flags.append(f"missing_section_heading:{section_name}")
    if any(x.get("duration_review") for x in _parse_stops(stops_raw)):
        quality_flags.append("negative_stop_duration_present_in_source")

    return {
        "wo_number": wo_number,
        "job_type": job_type,
        "maintenance_type": maintenance_type,
        "detected_structural_languages": detected_languages,
        "recognized_sections": recognized_sections,
        "identification": {
            "client": client, "wind_farm": wind_farm,
            "wind_turbine": wind_turbine, "machine": machine,
            "date_raw": date, "reason_for_work": reason,
        },
        "work_done": work_done or None,
        "alarms": _parse_alarms(alarms_raw),
        "other_data": _parse_other_data(other_raw),
        "failure_modes": _parse_failure_modes(failure_raw),
        "machine_stops": _parse_stops(stops_raw),
        "labor": _nonempty_lines(labor_raw),
        "materials": _nonempty_lines(materials_raw),
        "tools": _nonempty_lines(tools_raw),
        "raw_sections": {
            "alarms": alarms_raw, "other_data": other_raw,
            "failure_modes": failure_raw, "machine_stops": stops_raw,
            "labor": labor_raw, "materials": materials_raw, "tools": tools_raw,
        },
        "quality_flags": quality_flags,
        "source_pages": record["source_pages"],
        "raw_text": raw,
    }


def extract_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    pages: list[PageText] = []
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            # Mantém a ordem textual apresentada pelo documento de origem.
            pages.append(PageText(index + 1, page.get_text("text", sort=False)))
    grouped = split_os_pages(pages)
    if not grouped:
        raise ValueError(
            f"Nenhuma OS foi identificada em {pdf_path.name}. "
            "O cabeçalho pode estar em um novo idioma/layout ou o PDF pode não conter texto selecionável."
        )
    parsed = [parse_record(item) for item in grouped]
    for item in parsed:
        item["source_file"] = pdf_path.name
    return parsed

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="")
    temp.replace(path)


def write_outputs(records: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_data = json.dumps(records, ensure_ascii=False, indent=2)
    atomic_write_text(output_dir / "ordens_servico.json", json_data)

    columns = [
        "wo_number", "job_type", "maintenance_type", "detected_structural_languages", "client", "wind_farm",
        "wind_turbine", "machine", "date_raw", "reason_for_work", "work_done",
        "recognized_sections", "other_data", "failure_modes", "alarms", "machine_stops", "labor",
        "materials", "tools", "quality_flags", "source_file", "source_pages",
    ]
    csv_path = output_dir / "ordens_servico.csv"
    temp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for item in records:
            ident = item.get("identification", {})
            row = dict(item)
            row.update(ident)
            for key in ("detected_structural_languages", "recognized_sections", "other_data", "failure_modes", "alarms", "machine_stops", "labor", "materials", "tools", "quality_flags", "source_pages"):
                row[key] = json.dumps(item.get(key), ensure_ascii=False)
            writer.writerow(row)
    temp_path.replace(csv_path)
    LOG.info("JSON atualizado: %s", output_dir / "ordens_servico.json")
    LOG.info("CSV atualizado: %s", csv_path)


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data.get("files"), dict):
            raise ValueError("estrutura de estado inválida")
        return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Não foi possível ler o controle incremental {state_path}: {exc}") from exc


def run_local(input_dir: Path, output_dir: Path, recursive: bool = False, force: bool = False) -> None:
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Pasta de entrada não encontrada: {input_dir}")

    state_path = output_dir / "controle_processamento.json"
    state = _load_state(state_path)
    cached: dict[str, Any] = state["files"]
    pdfs = sorted(input_dir.rglob("*.pdf") if recursive else input_dir.glob("*.pdf"))
    pdfs = [p for p in pdfs if p.is_file() and not p.name.startswith("~$") and not p.name.endswith(".part")]
    LOG.info("Pasta de entrada: %s", input_dir)
    LOG.info("PDFs encontrados: %d", len(pdfs))

    found_keys = {p.relative_to(input_dir).as_posix() for p in pdfs}
    removed = set(cached) - found_keys
    for key in removed:
        cached.pop(key, None)
        LOG.info("Arquivo removido da origem; retirado da consolidação: %s", key)

    new_count = changed_count = skipped_count = error_count = 0
    for index, pdf in enumerate(pdfs, start=1):
        key = pdf.relative_to(input_dir).as_posix()
        try:
            stat = pdf.stat()
            signature = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            previous = cached.get(key, {})
            if not force and previous.get("signature") == signature and previous.get("sha256"):
                skipped_count += 1
                LOG.info("[%d/%d] Sem alterações; ignorado: %s", index, len(pdfs), pdf.name)
                continue

            file_hash = sha256_file(pdf)
            if not force and previous.get("sha256") == file_hash:
                previous["signature"] = signature
                skipped_count += 1
                LOG.info("[%d/%d] Conteúdo idêntico; metadados atualizados: %s", index, len(pdfs), pdf.name)
                continue

            LOG.info("[%d/%d] Processando: %s", index, len(pdfs), pdf.name)
            records = extract_pdf(pdf)
            cached[key] = {
                "source_file": pdf.name,
                "signature": signature,
                "sha256": file_hash,
                "processed_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
                "records": records,
            }
            if previous:
                changed_count += 1
            else:
                new_count += 1
        except Exception as exc:
            error_count += 1
            LOG.exception("Falha no arquivo %s; o restante continuará sendo processado: %s", pdf, exc)

    state["files"] = cached
    state["version"] = 1
    atomic_write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2))

    all_records: list[dict[str, Any]] = []
    for key in sorted(cached):
        all_records.extend(cached[key].get("records", []))
    all_records.sort(key=lambda row: (row.get("identification", {}).get("date_raw") or "", row.get("wo_number") or ""))
    write_outputs(all_records, output_dir)

    LOG.info(
        "Finalizado: %d OS consolidadas | %d novos | %d alterados | %d ignorados | %d erros.",
        len(all_records), new_count, changed_count, skipped_count, error_count,
    )
    if error_count:
        LOG.warning("Há arquivos com erro. Consulte o log acima; uma próxima execução tentará processá-los novamente.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrator local e multilíngue de PDFs de ordens de serviço."
    )
    parser.add_argument("--input-dir", type=Path, help="Pasta local sincronizada que contém os PDFs.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Pasta dos arquivos JSON/CSV e controle incremental.")
    parser.add_argument("--test-pdf", type=Path, help="Processa apenas um PDF para validar o parser.")
    parser.add_argument("--recursive", action="store_true", help="Procura PDFs também nas subpastas.")
    parser.add_argument("--force", action="store_true", help="Reprocessa todos os PDFs, mesmo sem alteração.")
    parser.add_argument("--verbose", action="store_true", help="Ativa log detalhado.")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    try:
        output_dir = args.output_dir or Path(os.getenv("OUTPUT_DIR", "output"))
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir

        if args.test_pdf:
            if not args.test_pdf.is_file():
                raise FileNotFoundError(f"PDF não encontrado: {args.test_pdf}")
            output_dir.mkdir(parents=True, exist_ok=True)
            records = extract_pdf(args.test_pdf)
            write_outputs(records, output_dir)
            LOG.info("Teste concluído: %d OS identificadas em %s.", len(records), args.test_pdf.name)
            return 0

        configured_input = args.input_dir or os.getenv("INPUT_DIR", "data/input")
        input_dir = Path(configured_input)
        if not input_dir.is_absolute():
            input_dir = Path.cwd() / input_dir
        run_local(input_dir, output_dir, args.recursive, args.force)
        return 0
    except Exception as exc:
        LOG.error("Execução interrompida: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
