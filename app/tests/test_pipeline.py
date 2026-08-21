from core.pipeline import make_pipeline_state, reset_pipeline, set_step, finish_pipeline

STEPS = [
    {'id': 'about', 'label': 'About'},
    {'id': 'db', 'label': 'DB'},
]

def test_reset_sets_pending_steps():
    state = make_pipeline_state(STEPS)
    reset_pipeline(
        state,
        STEPS,
        profile_url='https://x',
        depth='light',
        start_date='2026-08-01',
        end_date='2026-08-31',
    )
    assert state['profile_url'] == 'https://x'
    assert state['depth'] == 'light'
    assert state['start_date'] == '2026-08-01'
    assert state['end_date'] == '2026-08-31'
    assert state['running'] is False
    assert [s['status'] for s in state['steps']] == ['pending', 'pending']

def test_set_step_and_finish():
    state = make_pipeline_state(STEPS)
    reset_pipeline(state, STEPS)
    set_step(state, 'about', 'active')
    set_step(state, 'about', 'done')
    finish_pipeline(state, error=None)
    assert state['steps'][0]['status'] == 'done'
    assert state['error'] is None
    assert state['running'] is False
    assert state['finished_at'] is not None
