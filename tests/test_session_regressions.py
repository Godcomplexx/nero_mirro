from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.core.settings import Settings
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.aggregator.plugin import AggregatorPlugin, SessionState
from neuro_mirror.plugins.moca_test.plugin import MocaTestPlugin, MOCA_TASKS
from neuro_mirror.plugins.storage.plugin import StoragePlugin
from neuro_mirror.screening.moca_scoring import score_moca_task, summarize_moca_tasks
from neuro_mirror.utils.audio import VoiceRecorder


def test_migration_failure_preserves_legacy_then_retries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy = Path('runtime/screenings.jsonl')
    legacy.parent.mkdir()
    original = json.dumps({'user_id': 'u1', 'name': 'Person', 'score': 8}) + '\n'
    legacy.write_text(original, encoding='utf-8')
    with patch.object(Path, 'replace', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):
            StoragePlugin(EventBus())
    assert legacy.read_text(encoding='utf-8') == original
    assert not Path('runtime/deidentified/screenings.jsonl').exists()
    store = StoragePlugin(EventBus())
    assert not legacy.exists()
    assert json.loads(store.storage_path.read_text(encoding='utf-8')) == {'user_id': 'u1', 'score': 8}


def test_failed_report_write_does_not_change_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = StoragePlugin(EventBus())
    event = Event(topic=Topics.STORAGE_WRITE, source='test', payload={'score': 4})
    asyncio.run(store.handle_event(event))
    before = store.storage_path.read_bytes()
    with patch.object(Path, 'replace', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):
            asyncio.run(store.handle_event(event))
    assert len(store._items) == 1
    assert store.storage_path.read_bytes() == before


def test_corrupt_history_is_not_discarded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy = Path('runtime/screenings.jsonl')
    legacy.parent.mkdir()
    legacy.write_text('{"score": 1}\n{"broken":', encoding='utf-8')
    before = legacy.read_bytes()
    with pytest.raises(ValueError):
        StoragePlugin(EventBus())
    assert legacy.read_bytes() == before


def test_session_write_failure_rolls_back_memory(tmp_path):
    store = SessionStore(tmp_path / 'sessions.json')
    record = store.start(user_id='u1', scenario='hads', versions={})
    before = store.path.read_bytes()
    with patch.object(Path, 'replace', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):
            store.checkpoint(record['session_id'], {'next_index': 3})
    assert store.get(record['session_id']) == record
    assert store.path.read_bytes() == before


def test_events_reasons_and_legacy_sessions_are_redacted(tmp_path):
    store = SessionStore(tmp_path / 'sessions.json')
    record = store.start(user_id='u1', scenario='hads', versions={})
    sid = record['session_id']
    store.add_event(sid, 'test', {'nested': {'email': 'hidden@example.org'}, 'note': 'a@example.org'})
    store.interrupt(sid, 'Contact b@example.org')
    payload = json.loads(store.path.read_text(encoding='utf-8'))
    payload[0]['events'].append({'type': 'legacy', 'details': {'name': 'Person', 'text': 'c@example.org'}})
    store.path.write_text(json.dumps(payload), encoding='utf-8')
    loaded = SessionStore(store.path)
    assert '@example.org' not in store.path.read_text(encoding='utf-8')
    assert 'Person' not in json.dumps(loaded.get(sid))
    assert loaded.get(sid)['user_id'] == 'u1'


def test_corrupt_sessions_are_not_overwritten(tmp_path):
    path = tmp_path / 'sessions.json'
    path.write_text('[{"broken":', encoding='utf-8')
    with pytest.raises(ValueError):
        SessionStore(path)
    assert path.read_text(encoding='utf-8') == '[{"broken":'


def test_recorder_start_failure_closes_and_removes_wav(tmp_path):
    path = tmp_path / 'recording.wav'
    import os
    def mkstemp(**kwargs):
        return os.open(path, os.O_CREAT | os.O_RDWR), str(path)
    stream = Mock()
    stream.start.side_effect = RuntimeError('device lost')
    recorder = VoiceRecorder(sample_rate=16000, channels=1, max_seconds=1)
    with patch('neuro_mirror.utils.audio.tempfile.mkstemp', side_effect=mkstemp), \
         patch('neuro_mirror.utils.audio.sd', SimpleNamespace(InputStream=Mock(return_value=stream))):
        with pytest.raises(RuntimeError, match='device lost'):
            recorder.start()
    assert not path.exists()
    assert recorder._wave_file is None
    assert not recorder.recording
    stream.close.assert_called_once()


def test_resume_uses_current_permissions_and_ignores_late_events(tmp_path):
    async def run():
        store = SessionStore(tmp_path / 'sessions.json')
        bus = EventBus()
        sub = bus.subscribe(Topics.HADS_START)
        agg = AggregatorPlugin(bus, appearance_composer=Mock(), session_store=store, settings=Settings())
        agg._active_user_id = 'u1'
        old = store.start(user_id='u1', scenario='hads', versions={}, permissions={'audio': True})
        sid = old['session_id']
        store.interrupt(sid, 'stop')
        await agg.handle_event(Event(topic=Topics.UI_ACTION, source='test', payload={
            'action': 'resume_session', 'session_id': sid, 'audio_allowed': False}))
        assert (await sub.queue.get()).payload['audio_allowed'] is False
        assert store.get(sid)['permissions']['audio'] is False
        await agg.handle_event(Event(topic=Topics.SESSION_ERROR, source='test', payload={
            'session_id': 'older-session', 'reason': 'late error'}))
        await agg.handle_event(Event(topic=Topics.SESSION_CHECKPOINT, source='test', payload={
            'session_id': 'older-session', 'next_index': 10}))
        assert store.get(sid)['status'] == 'in_progress'
        assert store.get(sid)['checkpoint'] == {}
        await agg.handle_event(Event(topic=Topics.UI_ACTION, source='test', payload={'action': 'start_hads'}))
        assert len(store.list_for_user('u1')) == 1
        await agg.handle_event(Event(topic=Topics.USER_SELECTED, source='test', payload={'user_id': 'u2'}))
        assert store.get(sid)['status'] == 'interrupted'
        assert agg.state == SessionState.IDLE
    asyncio.run(run())


def test_moca_resume_without_current_audio_consent_keeps_checkpoint(tmp_path):
    async def run():
        store = SessionStore(tmp_path / 'sessions.json')
        record = store.start(user_id='u1', scenario='moca', versions={}, permissions={'audio': True})
        sid = record['session_id']
        store.checkpoint(sid, {'next_index': 1})
        store.interrupt(sid, 'stop')
        agg = AggregatorPlugin(EventBus(), appearance_composer=Mock(), session_store=store)
        agg._active_user_id = 'u1'
        await agg._resume_session(sid, {'audio_allowed': False})
        assert store.get(sid)['status'] == 'interrupted'
        assert store.get(sid)['checkpoint']['next_index'] == 1
        assert agg.state == SessionState.IDLE
    asyncio.run(run())


def test_video_screening_transitions_to_hads_without_audio(tmp_path):
    async def run():
        bus = EventBus()
        sub = bus.subscribe(Topics.HADS_START)
        agg = AggregatorPlugin(bus, appearance_composer=Mock())
        agg.state = SessionState.SCREENING
        agg._session_permissions = {'audio': False, 'video': True}
        agg._latest_results['video'] = {'heart_rate_status': 'unavailable'}
        with patch('asyncio.sleep', new_callable=AsyncMock):
            await agg._maybe_finish_screening()
        assert (await sub.queue.get()).payload['audio_allowed'] is False
        assert agg.state == SessionState.HADS
    asyncio.run(run())


def test_moca_restores_completed_tasks_and_rescores_with_current_algorithm():
    async def run():
        bus = EventBus()
        sub = bus.subscribe(Topics.MOCA_TEST_RESULT, Topics.SESSION_CHECKPOINT)
        plugin = MocaTestPlugin(bus, settings=Settings())
        plugin._session_id = 'resume-test'
        previous = [score_moca_task(task.task_id, 'тест') for task in MOCA_TASKS[:3]]
        previous[0]['score'] = 999  # A stale saved score must not affect the new algorithm.
        plugin._resume_checkpoint = {'next_index': 3, 'results': previous}
        plugin._speak = AsyncMock(return_value=True)
        plugin._record_and_transcribe = AsyncMock(return_value='тест')
        plugin._run_serial_subtraction = AsyncMock(return_value='93 | 86 | 79 | 72 | 65')
        with patch('asyncio.sleep', new_callable=AsyncMock):
            await plugin._run_test()
        events = []
        while not sub.queue.empty():
            events.append(sub.queue.get_nowait())
        checkpoints = [e.payload for e in events if e.topic == Topics.SESSION_CHECKPOINT]
        result = next(e.payload for e in events if e.topic == Topics.MOCA_TEST_RESULT)
        assert [c['next_index'] for c in checkpoints] == list(range(4, 12))
        assert all(c['session_id'] == 'resume-test' for c in checkpoints)
        assert len(result['tasks']) == 11
        expected = summarize_moca_tasks([score_moca_task(t.task_id,
            '93 | 86 | 79 | 72 | 65' if t.task_id == 'attention_serial' else 'тест') for t in MOCA_TASKS])
        assert result['score'] == expected['score']
        assert result['max_score'] == 15
        called = [call.args[0].task_id for call in plugin._record_and_transcribe.await_args_list]
        assert not set(called) & {t.task_id for t in MOCA_TASKS[:3]}
    asyncio.run(run())


def test_moca_worker_failure_is_not_scored_and_removes_audio(tmp_path):
    async def run():
        path = tmp_path / 'answer.wav'
        path.write_bytes(b'temporary audio')
        bus = Mock()
        bus.request = AsyncMock(return_value={'accepted': False, 'transcript': 'guess', 'message': 'worker failed'})
        plugin = MocaTestPlugin(bus, settings=Settings())
        with pytest.raises(RuntimeError, match='worker failed'):
            await plugin._transcribe(str(path))
        assert not path.exists()
    asyncio.run(run())


def test_serial_subtraction_does_not_score_missing_audio():
    async def run():
        plugin = MocaTestPlugin(EventBus(), settings=Settings())
        plugin._record_and_transcribe = AsyncMock(return_value='')
        task = next(t for t in MOCA_TASKS if t.task_id == 'attention_serial')
        with pytest.raises(RuntimeError):
            await plugin._run_serial_subtraction(task, 4, 11)
    asyncio.run(run())


def test_cancelled_recording_stops_microphone_and_removes_audio(tmp_path):
    async def run():
        path = tmp_path / 'answer.wav'
        path.write_bytes(b'temporary audio')
        recorder = Mock(available=True, recording=True)
        recorder.start.return_value = str(path)
        recorder.stop.return_value = str(path)
        plugin = MocaTestPlugin(EventBus(), settings=Settings())
        with patch('neuro_mirror.plugins.moca_test.plugin.VoiceRecorder', return_value=recorder), \
             patch('asyncio.sleep', new_callable=AsyncMock, side_effect=asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                await plugin._record_and_transcribe(MOCA_TASKS[0])
        recorder.stop.assert_called_once()
        assert not path.exists()
    asyncio.run(run())


def test_http_consents_cannot_be_overridden_by_action_body(tmp_path):
    from fastapi.testclient import TestClient
    from neuro_mirror.core.user_profiles import UserProfileStore
    from neuro_mirror.web.app import create_app
    users = UserProfileStore(tmp_path)
    user = users.create_user('Test', consent=False, personal_data_consent=True,
                             audio_data_consent=False, video_data_consent=False)
    users.select_user(user['id'])
    bus = SimpleNamespace(publish=AsyncMock())
    app = create_app()
    app.state.context = SimpleNamespace(user_store=users, runtime=SimpleNamespace(bus=bus))
    # No lifespan: route checks use real profiles with an isolated event transport.
    client = TestClient(app)
    for action in ('start_moca', 'start_screening', 'start_preview', 'start_voice_capture'):
        response = client.post(f'/api/actions/{action}', json={'audio_allowed': True, 'video_allowed': True})
        assert response.status_code == 403
    assert client.post('/api/actions/resume_session').status_code == 400
    response = client.post('/api/actions/start_hads', json={'action': 'resume_session', 'audio_allowed': True})
    assert response.status_code == 200
    published = bus.publish.await_args.args[0].payload
    assert published['action'] == 'start_hads'
    assert published['audio_allowed'] is False
    client.close()


def test_face_check_gracefully_reports_missing_detector(monkeypatch):
    import cv2
    import numpy as np
    from neuro_mirror.screening.session_check import analyze_frame_conditions
    image = np.full((240, 320, 3), 128, dtype=np.uint8)
    ok, encoded = cv2.imencode('.jpg', image)
    assert ok
    broken = Mock()
    broken.empty.return_value = True
    monkeypatch.setattr(cv2, 'CascadeClassifier', Mock(return_value=broken))
    result = analyze_frame_conditions(encoded.tobytes())
    assert result['frame_ok'] is True
    assert result['detector_available'] is False
    assert result['advice']
