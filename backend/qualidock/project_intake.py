"""Browse-first project intake using the existing analysis/sample configuration.

Names create new organizational identities; they never match existing biology.
"""
import asyncio

from .catalog import CatalogConflict
from .release_policy import digest


class ProjectIntake:
    def __init__(self, manager):
        self.manager = manager
        self.guard = asyncio.Lock()

    def register(self, project_id, run):
        catalog = self.manager.catalog
        inventory = self.manager.delivery.inspect(run['id'])['files']
        by_path = {file['path']: file for file in inventory}
        pairs = {row['path']: row for row in run['input_pairing']}
        with catalog.transaction(True) as db:
            sequencing = catalog.create_record(db, 'sequencing_run', {'display_name': run['name'], 'input_stage': 'unknown'}, project_id)
            assignments = []
            for group in run['sample_groups']:
                # The existing sample editor has already allowed explicit review and
                # correction of this group. Identical labels never merge records.
                sample = catalog.create_record(db, 'sample', {'display_name': group['display_name']}, project_id)
                for path in group['files']:
                    pair = pairs[path]
                    assignments.append({'file_id': by_path[path]['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'],
                        'read': pair.get('read') or ('SE' if pair.get('assignment') == 'single' else 'unpaired'),
                        'lane': pair.get('lane'), 'chunk': pair.get('chunk'), 'source': 'user_confirmed'})
            normalized = catalog.prepare_assignments(run['id'], assignments)
            link = catalog.link_record(db, project_id, run['id'], normalized)
            catalog.event(db, project_id, link['id'], 'browse_intake_confirmed', {'analysis_id': run['id'], 'sample_count': len(run['sample_groups']), 'file_count': len(assignments), 'grouping_source': 'User reviewed existing file/sample configuration; new organizational IDs, no biological auto-match'})
        return link

    async def start(self, project_id, request_key, **configuration):
        fingerprint = digest(configuration)
        async with self.guard:
            existing = next((run for run in self.manager.runs.values() if run.get('project_intake', {}).get('project_id') == project_id and run['project_intake'].get('request_key') == request_key), None)
            if existing:
                if existing['project_intake'].get('request_fingerprint') != fingerprint:
                    raise CatalogConflict('This request key belongs to different analysis settings; review the new selection')
                if existing['project_intake']['state'] != 'registered':
                    raise CatalogConflict('This request created analysis ' + existing['id'] + ' but registration did not complete. Inspect it in Analyses before retrying with a new selection.')
                return existing
            project = self.manager.catalog.detail(project_id)
            if project['declared']['status'] != 'active':
                raise ValueError('Restore the project before adding FASTQs')
            if configuration['mode'] not in {'fastqc', 'both'}:
                raise ValueError('Browse intake requires FASTQ analysis; attach existing report-only analyses separately')
            if configuration.get('input_pairing') is None or configuration.get('sample_groups') is None:
                raise ValueError('Review the selected sample groups and pairs before adding FASTQs')
            run = await self.manager.create(**configuration)
            self.manager.update(run, project_intake={'project_id': project_id, 'request_key': request_key, 'request_fingerprint': fingerprint, 'state': 'registering'})
            try:
                await asyncio.to_thread(self.register, project_id, run)
                self.manager.update(run, project_intake={**run['project_intake'], 'state': 'registered'})
            except Exception as exc:
                await self.manager.cancel(run['id'])
                self.manager.update(run, project_intake={**run['project_intake'], 'state': 'registration_failed'})
                raise ValueError('Project registration failed; analysis ' + run['id'] + ' remains in Analyses for inspection. No original FASTQs were changed.') from exc
            return run
