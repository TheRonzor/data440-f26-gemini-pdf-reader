'''Test structured extraction with one Gemini API call per PDF.'''

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError


ROOT = Path(__file__).resolve().parent
TEST_SYLLABI_DIR = ROOT / 'docs' / 'test_syllabi'
LOG_PATH = ROOT / 'logs' / 'gemini_syllabus_runs.jsonl'
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
RATE_LIMIT_DELAY_SECONDS = 4

PROMPT = '''Extract only information supported by this syllabus.
Return the fields required by the response schema.

List each grading category and its percentage of the final grade. Write a
short list of course objectives based on the syllabus, with one objective
per item and no bullet characters in the strings.

Put fixed assignment, exam, and project due dates in assignment_dates.
Put add/drop, withdrawal, holidays, and breaks in administrative_dates.
Keep date_text as written in the syllabus, including any date range.
Do not turn office hours or class meeting times into dates. Do not infer
missing due dates or add an entry for a date that is only "to be announced"
or available from another source. Use an empty list when a category has no
dates. Source pages are numbered starting at 1.'''


class GradeWeight(BaseModel):
	'''Represent one grading category and its weight.'''

	category: str = Field(description='Name of the grading category')
	percentage: float = Field(description='Percent of the final grade')
	source_page: int = Field(description='One-based source PDF page number')


class CourseDate(BaseModel):
	'''Represent one dated syllabus item.'''

	label: str = Field(description='Short name of the dated item')
	date_text: str = Field(description='Date or range as written in the PDF')
	source_page: int = Field(description='One-based source PDF page number')


class SyllabusExtraction(BaseModel):
	'''The fields required for a syllabus extraction.'''

	grade_weights: list[GradeWeight]
	objectives: list[str]
	assignment_dates: list[CourseDate]
	administrative_dates: list[CourseDate]


def parse_args() -> argparse.Namespace:
	'''Read an optional single PDF path and model name.'''

	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('pdf', nargs='?', type=Path)
	parser.add_argument('--model', default=DEFAULT_MODEL)
	return parser.parse_args()


def find_pdfs(pdf: Path | None) -> list[Path]:
	'''Find PDFs at run time, or select one PDF when specified.'''

	if pdf is not None:
		pdf_path = pdf.resolve()
		if not pdf_path.is_file() or pdf_path.suffix.lower() != '.pdf':
			raise ValueError(f'PDF file not found: {pdf_path}')
		return [pdf_path]

	if not TEST_SYLLABI_DIR.is_dir():
		raise ValueError(f'Syllabus directory not found: {TEST_SYLLABI_DIR}')

	# Sort the discovered files so repeated runs use the same order.
	pdf_paths = sorted(
		path for path in TEST_SYLLABI_DIR.iterdir()
		if path.is_file() and path.suffix.lower() == '.pdf'
	)
	if not pdf_paths:
		raise ValueError(f'No PDF files found in {TEST_SYLLABI_DIR}')
	return pdf_paths


def write_log(record: dict[str, object]) -> None:
	'''Append one outcome to the JSONL log.'''

	LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
	with LOG_PATH.open('a', encoding='utf-8') as log_file:
		log_file.write(json.dumps(record, ensure_ascii=False) + '\n')
	return None


def print_result(result: SyllabusExtraction) -> None:
	'''Show the extracted fields in a compact form.'''

	print('Grade weights:')
	for item in result.grade_weights:
		print(f'  - {item.category}: {item.percentage:g}% '
			f'(page {item.source_page})')

	print('Course objectives:')
	for objective in result.objectives:
		print(f'  - {objective}')

	for label, items in (
		('Assignment dates', result.assignment_dates),
		('Administrative dates', result.administrative_dates),
	):
		print(f'{label}: {len(items)}')
		for item in items:
			print(f'  - {item.label}: {item.date_text} '
				f'(page {item.source_page})')
	return None


def run_pdf(pdf_path: Path, model: str, api_key: str) -> bool:
	'''Make one API call for a PDF and record its outcome.'''

	started_at = datetime.now(timezone.utc).isoformat()
	start_time = time.perf_counter()
	status = 'client_error'
	http_status = None
	error_message = None
	usage = {}
	result = None
	client = None

	try:
		client = genai.Client(
			api_key=api_key,
			http_options=types.HttpOptions(
				retry_options=types.HttpRetryOptions(attempts=1),
			),
		)
		response = client.models.generate_content(
			model=model,
			contents=[
				types.Part.from_bytes(
					data=pdf_path.read_bytes(),
					mime_type='application/pdf',
				),
				PROMPT,
			],
			config=types.GenerateContentConfig(
				response_mime_type='application/json',
				response_schema=SyllabusExtraction,
			),
		)
		http_status = 200
		if response.usage_metadata is not None:
			usage = {
				'input_tokens': response.usage_metadata.prompt_token_count,
				'output_tokens': (
					response.usage_metadata.candidates_token_count
				),
				'total_tokens': response.usage_metadata.total_token_count,
			}
		if not response.text:
			status = 'empty_response'
			error_message = 'Gemini returned no text.'
		else:
			result = SyllabusExtraction.model_validate_json(response.text)
			status = 'success'
	except errors.APIError as error:
		status = 'api_error'
		http_status = error.code
		error_message = error.message
	except ValidationError as error:
		status = 'schema_error'
		error_message = str(error)
	except Exception as error:
		status = 'client_error'
		error_message = f'{type(error).__name__}: {error}'
	finally:
		if client is not None:
			client.close()

	if error_message is not None:
		error_message = error_message.replace(api_key, '[REDACTED]')
	record = {
		'started_at_utc': started_at,
		'elapsed_seconds': round(time.perf_counter() - start_time, 3),
		'pdf': str(pdf_path),
		'model': model,
		'status': status,
		'http_status': http_status,
		'usage': usage,
		'error': error_message,
		'result': result.model_dump() if result is not None else None,
	}
	write_log(record)
	print(f'PDF: {pdf_path.name}')
	print(f'Status: {status} (HTTP {http_status or "unknown"})')
	print(f'Elapsed: {record["elapsed_seconds"]} seconds')
	print(f'Log: {LOG_PATH}')
	if result is not None:
		print_result(result)
	else:
		print(f'Error: {error_message}')
	return status == 'success'


def main() -> int:
	'''Run each discovered PDF once and summarize the outcomes.'''

	args = parse_args()
	try:
		pdf_paths = find_pdfs(args.pdf)
	except ValueError as error:
		print(error)
		return 2

	load_dotenv(ROOT / '.env')
	api_key = os.getenv('GEMINI_API_KEY')
	if not api_key:
		print('Set GEMINI_API_KEY in the project .env file first.')
		return 2

	success_count = 0
	for index, pdf_path in enumerate(pdf_paths):
		print(f'\n[{index + 1}/{len(pdf_paths)}]')
		success_count += run_pdf(pdf_path, args.model, api_key)
		if index < len(pdf_paths) - 1:
			# Space requests using the delay already used by src/clients.py.
			time.sleep(RATE_LIMIT_DELAY_SECONDS)

	print(f'\nCompleted: {success_count}/{len(pdf_paths)} successful')
	return 0 if success_count == len(pdf_paths) else 1


if __name__ == '__main__':
	raise SystemExit(main())
