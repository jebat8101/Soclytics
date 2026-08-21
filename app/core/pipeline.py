from datetime import datetime

def make_pipeline_state(step_defs):
    return {
        'running': False,
        'profile_url': '',
        'depth': '',
        'start_date': None,
        'end_date': None,
        'steps': [],
        'error': None,
        'profile_id': None,
        'started_at': None,
        'finished_at': None,
    }

def reset_pipeline(state, step_defs, profile_url='', depth='', start_date=None, end_date=None):
    state.update({
        'running': False,
        'profile_url': profile_url,
        'depth': depth,
        'start_date': start_date,
        'end_date': end_date,
        'error': None,
        'profile_id': None,
        'started_at': None,
        'finished_at': None,
        'steps': [
            {'id': s['id'], 'label': s['label'], 'status': 'pending'}
            for s in step_defs
        ],
    })

def set_step(state, step_id, status):
    for s in state['steps']:
        if s['id'] == step_id:
            s['status'] = status
            break

def finish_pipeline(state, error=None):
    state['running'] = False
    state['error'] = error
    state['finished_at'] = datetime.utcnow().isoformat() + 'Z'
