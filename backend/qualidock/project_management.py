"""Declared metadata import and audited corrections, reusing the project registry."""
import csv
import io
import hashlib
import json
import re
import uuid

from .catalog import CatalogConflict, encoded, validate_fields
from .manager import now
from .release_policy import digest

CSV_FIELDS = {'display_name', 'declared_identifier', 'notes', 'assay', 'library_type', 'expected_yield_metric', 'expected_yield_minimum'}


def parse_samples(content, format):
    if not isinstance(content, str) or len(content.encode()) > 1024 * 1024:
        raise ValueError('Sample metadata import exceeds 1 MiB')
    if format == 'csv':
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff'), newline=''))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) - CSV_FIELDS:
            raise ValueError('Use unique supported metadata CSV headers')
        records = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Metadata CSV has an inconsistent number of columns')
            metric = row.pop('expected_yield_metric', '')
            minimum = row.pop('expected_yield_minimum', '')
            if metric or minimum:
                if not re.fullmatch('[0-9]+', minimum):
                    raise ValueError('Expected yield requires a plain nonnegative whole number')
                row['expected_yield'] = {'metric': metric, 'minimum': int(minimum)}
            records.append(row)
            if len(records) > 500:
                raise ValueError('Import at most 500 sample records at a time')
    elif format == 'json':
        records = json.loads(content)
    else:
        raise ValueError('Sample import format must be csv or json')
    if not isinstance(records, list) or not 1 <= len(records) <= 500 or any(not isinstance(row, dict) for row in records):
        raise ValueError('Import a nonempty array of at most 500 sample records')
    normalized = [validate_fields('sample', row, True) for row in records]
    identifiers = [row['declared_identifier'] for row in normalized if row.get('declared_identifier')]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Repeated declared identifiers are ambiguous; resolve them before importing')
    unnamed = [row['display_name'] for row in normalized if not row.get('declared_identifier')]
    if len(unnamed) != len(set(unnamed)):
        raise ValueError('Repeated names without explicit identifiers require manual resolution')
    return normalized


class ProjectManagement:
    def __init__(self, catalog):
        self.catalog = catalog

    def import_samples(self, project_id, content, format, fingerprint=None):
        rows = parse_samples(content, format)
        source_hash = hashlib.sha256(content.encode()).hexdigest()
        catalog = self.catalog
        with catalog.transaction(fingerprint is not None) as db:
            project = catalog.entity(db, project_id, 'project')
            if project['declared']['status'] != 'active':
                raise ValueError('Restore the archived project before importing metadata')
            imports = db.execute("SELECT data FROM events WHERE project_id=? AND action='samples_imported'", (project_id,)).fetchall()
            previous = next((json.loads(row[0]) for row in imports if json.loads(row[0]).get('submitted_text_sha256') == source_hash and json.loads(row[0]).get('source_format') == format), None)
            if previous and fingerprint is not None:
                return {**previous, 'reused': True}
            existing = [json.loads(row[0]) for row in db.execute("SELECT fields FROM entities WHERE project_id=? AND kind='sample'", (project_id,))]
            for row in rows:
                if any(row.get('declared_identifier') and old.get('declared_identifier') == row['declared_identifier'] or not row.get('declared_identifier') and old.get('display_name') == row['display_name'] for old in existing):
                    raise CatalogConflict('Sample metadata already contains a matching identifier/name; explicitly edit or resolve existing IDs instead of auto-matching')
            revision = db.execute('SELECT COALESCE(MAX(sequence),0) FROM events WHERE project_id=?', (project_id,)).fetchone()[0]
            current = digest({'project_id': project_id, 'source_hash': source_hash, 'rows': rows, 'catalog_revision': revision})
            if fingerprint is None:
                return {'fingerprint': current, 'submitted_text_sha256': source_hash, 'rows': rows, 'count': len(rows), 'identity_source': 'user_imported_declarations'}
            if fingerprint != current:
                raise CatalogConflict('Project metadata changed after the import preview; preview again')
            identifiers = []
            for fields in rows:
                entity_id = 'smp_' + uuid.uuid4().hex
                fields.setdefault('status', 'active')
                stamp = now()
                db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?)', (entity_id, 'sample', project_id, stamp, stamp, 1, encoded(fields)))
                catalog.event(db, project_id, entity_id, 'created', {'kind': 'sample', 'declared': fields, 'submitted_text_sha256': source_hash})
                identifiers.append(entity_id)
            result = {'submitted_text_sha256': source_hash, 'source_format': format, 'sample_ids': identifiers, 'count': len(identifiers), 'identity_source': 'user_imported_declarations'}
            catalog.event(db, project_id, project_id, 'samples_imported', result)
            return {**result, 'reused': False}

    @staticmethod
    def link(db, project_id, link_id):
        row = db.execute('SELECT * FROM analysis_links WHERE project_id=? AND id=?', (project_id, link_id)).fetchone()
        if row is None:
            raise ValueError('Unknown project analysis link')
        return dict(row)

    def inventory(self, project_id, link_id):
        catalog = self.catalog
        with catalog.transaction() as db:
            link = self.link(db, project_id, link_id)
            associations = [{**dict(row), **{key: json.loads(row[key]) for key in ('declared', 'observed', 'actor')}} for row in db.execute('SELECT * FROM associations WHERE analysis_link_id=? ORDER BY id', (link_id,))]
        data = catalog.manager.delivery.inspect(link['analysis_id'])
        keys = ('file_id', 'filename', 'report_id', 'read', 'lane', 'chunk', 'input_available', 'qc_snapshot_matches')
        return {'analysis_id': link['analysis_id'], 'files': [{key: file.get(key) for key in keys} for file in data['files']], 'associations': associations}

    def add_assignments(self, project_id, link_id, assignments):
        catalog = self.catalog
        with catalog.transaction() as db:
            link = self.link(db, project_id, link_id)
        normalized = catalog.prepare_assignments(link['analysis_id'], assignments)
        with catalog.transaction(True) as db:
            self.link(db, project_id, link_id)
            if catalog.entity(db, project_id, 'project')['declared']['status'] != 'active':
                raise ValueError('Restore the archived project before assigning files')
            catalog.write_assignments(db, project_id, link_id, normalized)
        return {'added': len(normalized)}

    def revise_assignment(self, project_id, association_id, revision, assignment, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError('A reason (1–2000 characters) is required to correct an identity association')
        catalog = self.catalog
        with catalog.transaction() as db:
            row = db.execute('SELECT * FROM associations WHERE id=? AND project_id=?', (association_id, project_id)).fetchone()
            if row is None:
                raise ValueError('Unknown project file association')
            previous = dict(row)
            link = self.link(db, project_id, row['analysis_link_id'])
        if assignment.get('file_id') != previous['file_id']:
            raise ValueError('An association revision cannot change its source file identity')
        normalized = catalog.prepare_assignments(link['analysis_id'], [assignment])[0]
        with catalog.transaction(True) as db:
            row = db.execute('SELECT * FROM associations WHERE id=? AND project_id=?', (association_id, project_id)).fetchone()
            if row['revision'] != revision:
                raise CatalogConflict('Association changed; reload before correcting it')
            if catalog.entity(db, project_id, 'project')['declared']['status'] != 'active':
                raise ValueError('Restore the archived project before correcting associations')
            for key, kind in [('sample_id', 'sample'), ('sequencing_run_id', 'sequencing_run')]:
                if catalog.entity(db, assignment[key], kind, project_id)['declared']['status'] != 'active':
                    raise ValueError('Choose active sample/run records')
            _, declared, observed = normalized
            db.execute('UPDATE associations SET sample_id=?,sequencing_run_id=?,declared=?,observed=?,revision=revision+1 WHERE id=?',
                       (assignment['sample_id'], assignment['sequencing_run_id'], encoded(declared), encoded(observed), association_id))
            current = dict(db.execute('SELECT * FROM associations WHERE id=?', (association_id,)).fetchone())
            catalog.event(db, project_id, association_id, 'association_corrected', {'previous': previous, 'current': current, 'reason': reason.strip()})
            return {**current, **{key: json.loads(current[key]) for key in ('declared', 'observed', 'actor')}}
