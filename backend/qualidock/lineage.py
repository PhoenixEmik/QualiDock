"""Bounded on-demand projection of existing manifests. No graph/index persistence."""
from . import datasets
from .files import PathViolation
from .integrity import snapshot

MAX_NODES, MAX_DEPTH, MAX_ITEMS = 20, 8, 50


def project(manager, run_id):
    manager.runs[run_id]  # Same authenticated analysis authority as the detail API.
    nodes, seen, visiting, warnings = [], set(), set(), []

    def visit(identity, depth):
        if identity in visiting:
            warnings.append(f'Cycle stopped at analysis {identity}')
            return 'cycle'
        if identity in seen: return 'recorded'
        if depth > MAX_DEPTH or len(seen) >= MAX_NODES:
            warnings.append('Ancestry limit reached; open a parent analysis to continue')
            return 'limit'
        run = manager.runs.get(identity)
        if run is None: return 'missing_parent'
        seen.add(identity); visiting.add(identity)
        inputs = run.get('inputs', [])
        provenance = run.get('input_provenance', [])
        refs = run.get('input_datasets', [])
        # Optional old records may retain copied provenance but no separate refs.
        if not refs:
            refs = [{'run_id':p.get('run_id'), 'dataset_id':p.get('dataset_id')} for p in provenance]
        edges, linked = [], {}
        for ref in refs[:MAX_ITEMS]:
            parent_id, dataset_id = ref.get('run_id'), ref.get('dataset_id')
            parent = manager.runs.get(parent_id)
            source = next((p for p in provenance if p.get('run_id')==parent_id and p.get('dataset_id')==dataset_id), None)
            edge = {'parent_id':parent_id, 'dataset_id':dataset_id, 'input_path':source.get('absolute_path') if source else None,
                    'read':source.get('read') if source else None, 'paired':source.get('paired') if source else None,
                    'lane':source.get('lane') if source else None, 'chunk':source.get('chunk') if source else None,
                    'recorded_sha256':source.get('sha256') if source else None, 'integrity':'recorded_reference_only'}
            entry = next((d for d in parent.get('derived_datasets',[]) if d.get('id')==dataset_id), None) if parent else None
            if not parent: edge['integrity']='missing_parent'
            elif not entry: edge['integrity']='missing_dataset'
            elif source:
                try:
                    expected = str(manager.directory(parent_id)/entry['path'])
                    if source.get('absolute_path') not in inputs or source.get('absolute_path')!=expected or any(source.get(key)!=entry.get(key) for key in ('sha256','read','paired','unit_id')):
                        edge['integrity']='inconsistent_reference'
                    else:
                        datasets.registered(manager,[ref])
                        edge['integrity']='metadata_matches_recorded_not_rehashed'
                except (ValueError, OSError, KeyError):
                    edge['integrity']='unavailable_or_changed'
            edge['ancestry'] = visit(parent_id,depth+1) if parent_id else 'missing_parent'
            edges.append(edge)
            if edge['input_path'] in inputs: linked[edge['input_path']]=edge['integrity']
        input_rows=[]
        for path in inputs[:MAX_ITEMS]:
            relationship=next((p for p in run.get('input_pairing',[]) if p.get('path')==path), {})
            integrity=linked.get(path,'not_revalidated')
            if path not in linked:
                metadata=next((p for p in run.get('input_metadata',[]) if p.get('path')==path), {})
                try:
                    resolved=manager.files.resolve(path)
                    current=snapshot(resolved.stat())
                    if not metadata or any(k not in metadata for k in current): integrity='historical_metadata_unavailable'
                    elif any(current[k]!=metadata.get(k) for k in current): integrity='unavailable_or_changed'
                    else: integrity='metadata_matches_recorded_not_rehashed'
                except (PathViolation,OSError): integrity='unavailable_or_changed'
            input_rows.append({'path':path,'parent_recorded':path in linked,'integrity':integrity,
                               **{k:relationship.get(k) for k in ('read','paired','mate','lane','chunk')}})
        options=dict(run.get('processing',{}).get('options',{}))
        if 'identifiers' in options: options['requested_identifier_count']=len(options.pop('identifiers'))
        outputs=[{k:d.get(k) for k in ('id','path','source','read','paired','unit_id','records','bases','sha256')} for d in run.get('derived_datasets',[])[:MAX_ITEMS]]
        nodes.append({'id':identity,'name':run.get('name',identity),'mode':run.get('mode'),'state':run.get('state'),
                      'tools':{name:info.get('version') for name,info in run.get('tools',{}).items()},
                      'processors':[u['processor'] for u in run.get('processing',{}).get('units',[])[:MAX_ITEMS] if u.get('processor')],
                      'parameters':{**run.get('parameters',{}),**options},'inputs':input_rows,'parents':edges,
                      'derived_datasets':outputs,'rerun_of':run.get('rerun_of'), 'source_run_id':run.get('source_run_id'),
                      'report_count':len(run.get('reports',[])),
                      'omitted_inputs':max(0,len(inputs)-MAX_ITEMS),'omitted_datasets':max(0,len(run.get('derived_datasets',[]))-MAX_ITEMS),
                      'omitted_parents':max(0,len(refs)-MAX_ITEMS)})
        visiting.remove(identity)
        return 'recorded'

    visit(run_id,0)
    return {'root_id':run_id,'nodes':nodes,'warnings':list(dict.fromkeys(warnings)),
            'scope':'Recorded provenance; metadata checks are not fresh content hashes or full FASTQ validation',
            'limits':{'nodes':MAX_NODES,'depth':MAX_DEPTH,'items_per_analysis':MAX_ITEMS}}
