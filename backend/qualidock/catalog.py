"""Small project registry; QC/release manifests remain the scientific source of truth.

SQLite is used only for transactional domain relationships and append-only snapshots.
The existing default result-store lock owns this database. No FASTQ bytes are stored.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from .files import PathViolation
from .manager import now
from .release_policy import digest

SCHEMA_VERSION = 1
KINDS = {'project': 'prj', 'sample': 'smp', 'sequencing_run': 'seq'}
COMMON = {'display_name', 'declared_identifier', 'notes', 'status'}
FIELDS = {
    'project': COMMON,
    'sample': COMMON | {'assay', 'library_type', 'expected_yield'},
    'sequencing_run': COMMON | {'platform', 'sequenced_at', 'input_stage'},
}


class CatalogConflict(ValueError):
    """An optimistic revision or explicit domain relationship conflicts."""


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate_fields(kind, fields, creating=False):
    if kind not in FIELDS or set(fields) - FIELDS[kind]:
        raise ValueError('Unsupported domain field')
    for key, value in fields.items():
        if key == 'expected_yield':
            if value is not None and (not isinstance(value, dict) or set(value) != {'metric', 'minimum'} or not isinstance(value['metric'], str) or value['metric'] not in {'reads', 'read_pairs', 'bases'} or type(value['minimum']) is not int or not 0 <= value['minimum'] <= 2**53-1):
                raise ValueError('Expected yield requires explicit reads/read_pairs/bases and a nonnegative safe integer')
        elif not isinstance(value, str) or len(value) > (2000 if key == 'notes' else 200) or '\x00' in value:
            raise ValueError('Domain fields require bounded text')
    if (creating or 'display_name' in fields) and not fields.get('display_name', '').strip():
        raise ValueError('A display name is required')
    if fields.get('status', 'active') not in {'active', 'archived'}:
        raise ValueError('Status must be active or archived')
    if fields.get('input_stage', 'unknown') not in {'unknown', 'raw_fastq', 'upstream_processed'}:
        raise ValueError('Choose a declared input stage')
    if fields.get('sequenced_at'):
        from datetime import date
        date.fromisoformat(fields['sequenced_at'])
    return deepcopy(fields)


class ProjectCatalog:
    def __init__(self, manager):
        self.manager = manager
        self.path = manager.stores.default / 'projects.sqlite3'
        self.identity = None

    def check_path(self):
        self.manager.stores.resolve()
        if self.path.parent.stat().st_mode & 0o022:
            raise PathViolation('Project storage directory must not be writable by other users')
        for path in [self.path, *[Path(str(self.path) + suffix) for suffix in ('-journal', '-wal', '-shm')]]:
            if path.is_symlink():
                raise PathViolation('Project database contains an unsafe filesystem link')
            if path.exists():
                info = path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                    raise PathViolation('Project database must be a private regular file owned by the current user')
        if self.identity is not None:
            info = self.path.stat()
            if (info.st_dev, info.st_ino) != self.identity:
                raise PathViolation('Project database was replaced; restart to reacquire ownership')

    @contextmanager
    def transaction(self, write=False):
        self.check_path()
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ValueError('Unsupported project schema; restore a matching backup/application version')
            if connection.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise ValueError('Project storage requires SQLite rollback/DELETE journaling')
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def start(self):
        self.check_path()
        created = not self.path.exists()
        if created:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        self.check_path()
        with sqlite3.connect(self.path) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError('Project schema is newer than this application; downgrade refused without changing existing data')
            if version == 0:
                if not created or db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError('Unversioned project database requires recovery from backup')
                db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE entities (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, project_id TEXT REFERENCES entities(id),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL,
                    fields TEXT NOT NULL);
                CREATE INDEX entity_project ON entities(project_id, kind);
                CREATE TABLE analysis_links (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES entities(id),
                    analysis_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, actor TEXT NOT NULL);
                CREATE INDEX analysis_project ON analysis_links(project_id);
                CREATE TABLE associations (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES entities(id),
                    sample_id TEXT NOT NULL REFERENCES entities(id),
                    sequencing_run_id TEXT NOT NULL REFERENCES entities(id),
                    analysis_link_id TEXT NOT NULL REFERENCES analysis_links(id),
                    file_id TEXT NOT NULL, declared TEXT NOT NULL, observed TEXT NOT NULL,
                    created_at TEXT NOT NULL, actor TEXT NOT NULL,
                    UNIQUE(analysis_link_id, file_id));
                CREATE INDEX association_project ON associations(project_id, sample_id, sequencing_run_id);
                CREATE TABLE evidence (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES entities(id),
                    analysis_link_id TEXT NOT NULL REFERENCES analysis_links(id),
                    created_at TEXT NOT NULL, actor TEXT NOT NULL, sha256 TEXT NOT NULL,
                    snapshot TEXT NOT NULL, summary TEXT NOT NULL, UNIQUE(analysis_link_id, sha256));
                CREATE TABLE events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL REFERENCES entities(id), entity_id TEXT NOT NULL,
                    action TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TRIGGER evidence_no_update BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT,'Evidence is append-only'); END;
                CREATE TRIGGER evidence_no_delete BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT,'Evidence is append-only'); END;
                CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Audit is append-only'); END;
                CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Audit is append-only'); END;
                PRAGMA user_version=1;
                COMMIT;
                ''')
        info = self.path.stat()
        self.identity = (info.st_dev, info.st_ino)

    @staticmethod
    def entity(db, entity_id, kind=None, project_id=None):
        row = db.execute('SELECT * FROM entities WHERE id=?', (entity_id,)).fetchone()
        if row is None:
            raise KeyError(entity_id)
        if kind is not None and row['kind'] != kind or project_id is not None and row['project_id'] != project_id:
            raise ValueError('Invalid entity kind or cross-project reference')
        return {key: value for key, value in dict(row).items() if key != 'fields'} | {'declared': json.loads(row['fields'])}

    def event(self, db, project_id, entity_id, action, data):
        db.execute('INSERT INTO events(id,project_id,entity_id,action,created_at,actor,data) VALUES(?,?,?,?,?,?,?)',
                   (uuid.uuid4().hex, project_id, entity_id, action, now(), encoded(self.manager.delivery.actor()), encoded(data)))

    def create(self, kind, fields, project_id=None):
        fields = validate_fields(kind, fields, True)
        fields.setdefault('status', 'active')
        entity_id = KINDS[kind] + '_' + uuid.uuid4().hex
        stamp = now()
        with self.transaction(True) as db:
            if kind != 'project':
                project = self.entity(db, project_id, 'project')
                if project['declared']['status'] == 'archived':
                    raise ValueError('Restore the archived project before adding records')
            elif project_id is not None:
                raise ValueError('A project cannot belong to another project')
            db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?)', (entity_id, kind, project_id, stamp, stamp, 1, encoded(fields)))
            self.event(db, project_id or entity_id, entity_id, 'created', {'kind': kind, 'declared': fields})
            return self.entity(db, entity_id)

    def edit(self, entity_id, revision, fields, project_id=None):
        with self.transaction(True) as db:
            entity = self.entity(db, entity_id)
            if project_id is not None and entity['project_id'] != project_id:
                raise ValueError('Cross-project modification is not permitted')
            if type(revision) is not int or revision != entity['revision']:
                raise CatalogConflict('Project metadata changed; reload before editing')
            changes = validate_fields(entity['kind'], fields)
            merged = {**entity['declared'], **changes}
            db.execute('UPDATE entities SET fields=?,updated_at=?,revision=revision+1 WHERE id=?', (encoded(merged), now(), entity_id))
            self.event(db, entity['project_id'] or entity_id, entity_id, 'updated', {'previous_revision': revision, 'changes': changes})
            return self.entity(db, entity_id)

    def listing(self, kind='project', project_id=None, search='', offset=0, limit=25, status='active'):
        if kind not in KINDS or not 1 <= limit <= 100 or offset < 0 or len(search) > 200 or status not in {'all', 'active', 'archived'}:
            raise ValueError('Invalid project listing options')
        with self.transaction() as db:
            if project_id is not None:
                self.entity(db, project_id, 'project')
            # Bounded response; JSON is parsed only for the requested page. LIKE
            # metacharacters are escaped so a user's literal search stays literal.
            where = 'kind=? AND project_id IS ?'
            args = [kind, project_id]
            escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            where += " AND fields LIKE ? ESCAPE '\\'"
            args.append('%' + escaped + '%')
            if status != 'all':
                # Avoid a dependency on optional SQLite JSON extensions.
                where += ' AND fields LIKE ?'
                args.append('%"status":"' + status + '"%')
            total = db.execute('SELECT COUNT(*) FROM entities WHERE ' + where, args).fetchone()[0]
            ids = db.execute('SELECT id FROM entities WHERE ' + where + ' ORDER BY created_at DESC,id LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
            return {'items': [self.entity(db, row['id']) for row in ids], 'total': total, 'offset': offset, 'limit': limit}

    def detail(self, project_id):
        with self.transaction() as db:
            project = self.entity(db, project_id, 'project')
            counts = {row['kind']: row['n'] for row in db.execute('SELECT kind,COUNT(*) AS n FROM entities WHERE project_id=? GROUP BY kind', (project_id,))}
            counts['analyses'] = db.execute('SELECT COUNT(*) FROM analysis_links WHERE project_id=?', (project_id,)).fetchone()[0]
            counts['associations'] = db.execute('SELECT COUNT(*) FROM associations WHERE project_id=?', (project_id,)).fetchone()[0]
            return {**project, 'counts': counts, 'qc_readiness': 'unknown', 'release_readiness': 'unknown'}

    def associations(self, project_id, offset=0, limit=100):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid association pagination')
        with self.transaction() as db:
            self.entity(db, project_id, 'project')
            total = db.execute('SELECT COUNT(*) FROM associations WHERE project_id=?', (project_id,)).fetchone()[0]
            rows = db.execute('SELECT * FROM associations WHERE project_id=? ORDER BY created_at,id LIMIT ? OFFSET ?', (project_id, limit, offset)).fetchall()
            return {'items': [{**dict(row), **{key: json.loads(row[key]) for key in ('declared', 'observed', 'actor')}} for row in rows], 'total': total, 'offset': offset, 'limit': limit}

    def links(self, project_id, offset=0, limit=25):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid analysis-link pagination')
        with self.transaction() as db:
            self.entity(db, project_id, 'project')
            total = db.execute('SELECT COUNT(*) FROM analysis_links WHERE project_id=?', (project_id,)).fetchone()[0]
            rows = db.execute('SELECT * FROM analysis_links WHERE project_id=? ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (project_id, limit, offset)).fetchall()
            items = []
            for row in rows:
                run = self.manager.runs.get(row['analysis_id'])
                items.append({**dict(row), 'actor': json.loads(row['actor']), 'analysis': {key: run.get(key) for key in ('id', 'name', 'mode', 'state', 'created_at', 'finished_at')} if run else None})
            return {'items': items, 'total': total, 'offset': offset, 'limit': limit}

    def attach(self, project_id, analysis_id, assignments):
        run = self.manager.runs[analysis_id]
        self.manager.directory(analysis_id)  # Reuse result-store authorization.
        if not isinstance(assignments, list) or len(assignments) > 500:
            raise ValueError('At most 500 explicit file associations are supported')
        files = {file['file_id']: file for file in self.manager.delivery.inspect(analysis_id)['files']} if assignments else {}
        seen = set()
        normalized = []
        for assignment in assignments:
            if not isinstance(assignment, dict):
                raise ValueError('Each association must be an object')
            if set(assignment) - {'file_id', 'sample_id', 'sequencing_run_id', 'lane', 'chunk', 'library_identifier', 'read', 'source'}:
                raise ValueError('Unknown file association fields')
            file_id = assignment.get('file_id')
            if any(not isinstance(assignment.get(key), str) for key in ('file_id', 'sample_id', 'sequencing_run_id')):
                raise ValueError('Explicit file, sample and sequencing-run IDs are required')
            if file_id not in files or file_id in seen:
                raise ValueError('Associate each known analysis file once; duplicate or ambiguous assignment')
            seen.add(file_id)
            file = files[file_id]
            # A new explicit identity association must refer to an authorized,
            # readable source. Existing saved relationships remain inspectable if
            # source data later goes offline; project APIs never disclose paths.
            path = self.manager.files.resolve(file['path'])
            self.manager.readable_fastq(path)
            if not file['input_available']:
                raise PathViolation('Associated source is not currently accessible')
            declared = {key: assignment.get(key) for key in ('lane', 'chunk', 'library_identifier', 'read', 'source')}
            declared['source'] = declared['source'] or 'user_confirmed'
            if any(value is not None and (not isinstance(value, str) or len(value) > 200) for value in declared.values()):
                raise ValueError('Association metadata exceeds supported bounds')
            if declared['source'] not in {'user_confirmed', 'user_assigned'} or declared['read'] not in {None, 'R1', 'R2', 'SE', 'unpaired'}:
                raise ValueError('Identity associations must be explicitly user-confirmed or user-assigned')
            observed = {key: file.get(key) for key in ('file_id', 'filename', 'report_id', 'source_snapshot', 'qc_snapshot_matches', 'integrity_state', 'sha256')}
            normalized.append((assignment, declared, observed))
        with self.transaction(True) as db:
            project = self.entity(db, project_id, 'project')
            if project['declared']['status'] == 'archived':
                raise ValueError('Restore the archived project before linking analyses')
            old = db.execute('SELECT * FROM analysis_links WHERE analysis_id=?', (analysis_id,)).fetchone()
            if old:
                raise CatalogConflict('Analysis is already linked; historical relationships cannot be silently reassigned')
            for assignment, _, _ in normalized:
                self.entity(db, assignment.get('sample_id'), 'sample', project_id)
                self.entity(db, assignment.get('sequencing_run_id'), 'sequencing_run', project_id)
            link_id = 'lnk_' + uuid.uuid4().hex
            stamp = now()
            actor = encoded(self.manager.delivery.actor())
            db.execute('INSERT INTO analysis_links VALUES(?,?,?,?,?)', (link_id, project_id, analysis_id, stamp, actor))
            for assignment, declared, observed in normalized:
                db.execute('INSERT INTO associations VALUES(?,?,?,?,?,?,?,?,?,?)',
                           ('asc_' + uuid.uuid4().hex, project_id, assignment['sample_id'], assignment['sequencing_run_id'], link_id, assignment['file_id'], encoded(declared), encoded(observed), stamp, actor))
            self.event(db, project_id, link_id, 'analysis_linked', {'analysis_id': analysis_id, 'associations': len(normalized)})
            return {'id': link_id, 'project_id': project_id, 'analysis_id': run['id'], 'created_at': stamp, 'association_count': len(normalized)}

    def capture(self, project_id, link_id, sample_ids=None):
        revision = self.manager.revision
        with self.transaction() as db:
            row = db.execute('SELECT * FROM analysis_links WHERE id=? AND project_id=?', (link_id, project_id)).fetchone()
            if row is None:
                raise ValueError('Unknown project analysis link')
            analysis_id = row['analysis_id']
            associations = [dict(row) for row in db.execute('SELECT id,sample_id,sequencing_run_id,file_id,declared FROM associations WHERE analysis_link_id=? ORDER BY id', (link_id,))]
            declared_entities = {entity_id: self.entity(db, entity_id) for association in associations for entity_id in (association['sample_id'], association['sequencing_run_id'])}
        run = deepcopy(self.manager.runs[analysis_id])
        if run['state'] in {'running', 'queued'}:
            raise ValueError('Wait for terminal QC state before capturing immutable evidence')
        self.manager.directory(analysis_id)
        artifacts = []
        for report in run.get('reports', []):
            # Store references plus content digest, never report content/HTML or
            # executable command arguments containing private filesystem paths.
            if report['path'] != 'metrics.json':
                continue
            path = self.manager.artifact(analysis_id, report['path'])
            from .metrics import bounded_text
            artifacts.append({'artifact': report['path'], 'sha256': hashlib.sha256(bounded_text(path).encode()).hexdigest()})
        snapshot = {'schema_version': 1, 'analysis_id': analysis_id, 'state': run['state'], 'created_at': run['created_at'], 'finished_at': run.get('finished_at'),
                    'tools': {name: info.get('version') for name, info in run.get('tools', {}).items()},
                    'parameters': {key: value for key, value in run.get('parameters', {}).items() if key in {'threads', 'memory_mb', 'executor'}},
                    'associations': [{**record, 'declared': json.loads(record['declared'])} for record in associations],
                    'declared_entities': declared_entities, 'qc_artifacts': artifacts, 'release': None}
        if sample_ids is not None:
            evaluation = self.manager.release.inspect(analysis_id, sample_ids, run)
            snapshot['release'] = {key: evaluation[key] for key in ('evaluator_version', 'fingerprint', 'sample_ids', 'file_ids', 'readiness', 'review_state', 'decision', 'active_waivers', 'policy')}
        fingerprint = digest(snapshot)
        with self.transaction(True) as db:
            if revision != self.manager.revision or any(self.entity(db, entity_id)['revision'] != entity['revision'] for entity_id, entity in declared_entities.items()):
                raise CatalogConflict('QC or declared metadata changed during evidence capture; retry with current evidence')
            old = db.execute('SELECT id FROM evidence WHERE analysis_link_id=? AND sha256=?', (link_id, fingerprint)).fetchone()
            if old:
                return self.evidence_record(db, old['id'])
            evidence_id = 'evd_' + uuid.uuid4().hex
            release = snapshot['release'] or {}
            summary = {'analysis_id': analysis_id, 'qc_state': run['state'], 'readiness': release.get('readiness', 'unknown'), 'review_state': release.get('review_state', 'unknown'), 'decision_id': (release.get('decision') or {}).get('id'), 'association_count': len(associations)}
            db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)', (evidence_id, project_id, link_id, now(), encoded(self.manager.delivery.actor()), fingerprint, encoded(snapshot), encoded(summary)))
            self.event(db, project_id, evidence_id, 'evidence_captured', {'analysis_link_id': link_id, 'sha256': fingerprint})
            return self.evidence_record(db, evidence_id)

    @staticmethod
    def evidence_record(db, evidence_id):
        row = db.execute('SELECT * FROM evidence WHERE id=?', (evidence_id,)).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return {**dict(row), 'actor': json.loads(row['actor']), 'snapshot': json.loads(row['snapshot']), 'summary': json.loads(row['summary'])}

    def evidence_page(self, project_id, offset=0, limit=25):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid evidence pagination')
        with self.transaction() as db:
            self.entity(db, project_id, 'project')
            total = db.execute('SELECT COUNT(*) FROM evidence WHERE project_id=?', (project_id,)).fetchone()[0]
            rows = db.execute('SELECT id,project_id,analysis_link_id,created_at,actor,sha256,summary FROM evidence WHERE project_id=? ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (project_id, limit, offset)).fetchall()
            return {'items': [{**dict(row), 'actor': json.loads(row['actor']), 'summary': json.loads(row['summary'])} for row in rows], 'total': total, 'offset': offset, 'limit': limit}

    def evidence(self, project_id, evidence_id):
        with self.transaction() as db:
            result = self.evidence_record(db, evidence_id)
            if result['project_id'] != project_id:
                raise ValueError('Cross-project evidence access is not permitted')
            self.manager.directory(result['snapshot']['analysis_id'])
            return result

    def unassigned(self, offset=0, limit=25):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid unassigned pagination')
        with self.transaction() as db:
            assigned = {row[0] for row in db.execute('SELECT analysis_id FROM analysis_links')}
        runs = [run for run in self.manager.list() if run['id'] not in assigned]
        return {'items': [{key: run.get(key) for key in ('id', 'name', 'state', 'mode', 'created_at')} for run in runs[offset:offset+limit]], 'total': len(runs), 'offset': offset, 'limit': limit}
