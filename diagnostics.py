'''Inspect individual syllabus extraction records in JSONL logs.'''

import json
from dataclasses import dataclass
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent / 'logs'


@dataclass(frozen=True)
class LogEntry:
	'''Identify one run record and retain its original JSON text.'''

	source: Path
	line_number: int
	label: str
	raw_line: str


def load_logs() -> list[LogEntry]:
	'''List every nonblank run record in the available JSONL files.'''

	entries = []
	for source in sorted(LOG_DIR.glob('*.jsonl')):
		if not source.is_file():
			continue
		with source.open('r', encoding='utf-8') as log_file:
			for line_number, raw_line in enumerate(log_file, start=1):
				if not raw_line.strip():
					continue

				location = f'{source.name}:{line_number}'
				try:
					record = json.loads(raw_line)
				except json.JSONDecodeError:
					label = f'{location} | invalid JSON'
				else:
					if isinstance(record, dict):
						pdf_name = Path(str(record.get('pdf') or '')).name
						label = (
							f'{location} | {pdf_name or "unknown PDF"} | '
							f'{record.get("status") or "unknown status"}'
						)
					else:
						label = f'{location} | non-object JSON'

				entries.append(
					LogEntry(source, line_number, label, raw_line)
				)
	return entries


def print_log(entry: LogEntry) -> None:
	'''Parse and pretty-print one selected run record.'''

	print(entry.label)
	try:
		record = json.loads(entry.raw_line)
	except json.JSONDecodeError as error:
		print(
			f'Invalid JSON at {entry.source}:{entry.line_number}: '
			f'{error}'
		)
		return None

	print(json.dumps(record, indent=2, ensure_ascii=False))
	return None
