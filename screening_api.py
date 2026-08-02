"""
screening_api.py
----------------
Provides the Flask Blueprint for the SET Screening & AI Top 10 Stock Selection endpoints.
"""
import json
import threading
import time
from flask import Blueprint, request, jsonify
from screening_engine import run_screening, get_default_date, resolve_date
from ai_ranking_engine import run_ai_stock_selection, DEFAULT_WEIGHTS

screening_bp = Blueprint('screening', __name__)

# ── Shared state for standard screening ──────────────────────────────────────
_progress = {'current': 0, 'total': 0, 'running': False, 'done': False}
_results_store = {}
_lock = threading.Lock()

def _progress_callback(current, total):
    with _lock:
        _progress['current'] = current
        _progress['total'] = total

@screening_bp.route('/api/screen', methods=['POST'])
def start_screening():
    """Kick off the technical screening in a background thread."""
    global _results_store

    data = request.get_json() or {}
    date_str = data.get('date', str(get_default_date()))
    rsi = int(data.get('rsi', 30))
    stoch = int(data.get('stoch', 70))

    with _lock:
        if _progress['running']:
            return jsonify({'error': 'Screening already in progress'}), 409
        _progress['running'] = True
        _progress['done'] = False
        _progress['current'] = 0
        _progress['total'] = 0
        _results_store = {}

    def _run():
        global _results_store
        try:
            result = run_screening(date_str, rsi, stoch, progress_callback=_progress_callback)
            with _lock:
                _results_store = result
        except Exception as e:
            with _lock:
                _results_store = {'error': str(e)}
        finally:
            with _lock:
                _progress['running'] = False
                _progress['done'] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    resolved, msg = resolve_date(date_str)
    return jsonify({'status': 'started', 'date_message': msg, 'resolved_date': resolved})


@screening_bp.route('/api/progress')
def get_progress():
    """Polling endpoint — returns current technical screening progress as JSON."""
    with _lock:
        current = _progress['current']
        total = _progress['total']
        done = _progress['done']
    
    pct = int((current / total) * 100) if total > 0 else 0
    return jsonify({
        'current': current,
        'total': total,
        'pct': pct,
        'done': done
    })


@screening_bp.route('/api/results')
def get_results():
    """Return the technical screening results."""
    with _lock:
        if _progress['running']:
            return jsonify({'error': 'Still running'}), 202
        return jsonify(_results_store)


# ── AI Top 10 Selection Endpoints ──────────────────────────────────────────
_ai_progress = {'stage': 1, 'current': 0, 'total': 0, 'running': False, 'done': False, 'message': ''}
_ai_results_store = {}
_ai_lock = threading.Lock()

def _ai_progress_callback(info):
    with _ai_lock:
        _ai_progress['stage'] = info.get('stage', 1)
        _ai_progress['current'] = info.get('current', 0)
        _ai_progress['total'] = info.get('total', 100)
        _ai_progress['message'] = info.get('message', '')

@screening_bp.route('/api/ai_rank/start', methods=['POST'])
def start_ai_ranking():
    """Kick off multi-stage AI Stock Selection in background thread."""
    global _ai_results_store

    data = request.get_json() or {}
    weights = {
        'weight_tech': float(data.get('weight_tech', 0.40)),
        'weight_fund': float(data.get('weight_fund', 0.40)),
        'weight_mom': float(data.get('weight_mom', 0.15)),
        'weight_news': float(data.get('weight_news', 0.05))
    }
    date_str = data.get('date', str(get_default_date()))
    rsi = int(data.get('rsi', 30))
    stoch = int(data.get('stoch', 70))
    min_criteria = int(data.get('min_criteria', 4))
    set50_only = bool(data.get('set50_only', False))
    index_filter = str(data.get('index_filter', 'set50' if set50_only else 'all')).lower()
    process_all = bool(data.get('process_all', True))

    with _ai_lock:
        if _ai_progress['running']:
            return jsonify({'error': 'AI Ranking already in progress'}), 409
        _ai_progress['running'] = True
        _ai_progress['done'] = False
        _ai_progress['stage'] = 1
        _ai_progress['current'] = 0
        _ai_progress['total'] = 100
        idx_lbl = f" ({index_filter.upper()} Index)" if index_filter != "all" else ""
        _ai_progress['message'] = f'Initializing AI Analysis Pipeline (Min {min_criteria} Criteria{idx_lbl})...'
        _ai_results_store = {}

    def _run_ai():
        global _ai_results_store
        try:
            res = run_ai_stock_selection(
                weights=weights,
                date_str=date_str,
                rsi=rsi,
                stoch=stoch,
                min_criteria=min_criteria,
                set50_only=set50_only,
                index_filter=index_filter,
                process_all=process_all,
                progress_callback=_ai_progress_callback
            )
            with _ai_lock:
                _ai_results_store = res
        except Exception as e:
            with _ai_lock:
                _ai_results_store = {'status': 'error', 'message': str(e)}
        finally:
            with _ai_lock:
                _ai_progress['running'] = False
                _ai_progress['done'] = True

    t = threading.Thread(target=_run_ai, daemon=True)
    t.start()

    return jsonify({'status': 'started', 'weights': weights})


@screening_bp.route('/api/ai_rank/progress')
def get_ai_progress():
    """Polling endpoint for AI Selection pipeline."""
    with _ai_lock:
        stage = _ai_progress['stage']
        current = _ai_progress['current']
        total = _ai_progress['total']
        done = _ai_progress['done']
        running = _ai_progress['running']
        message = _ai_progress['message']

    pct = int((current / total) * 100) if total > 0 else 0
    return jsonify({
        'stage': stage,
        'current': current,
        'total': total,
        'pct': pct,
        'running': running,
        'done': done,
        'message': message
    })


@screening_bp.route('/api/ai_rank/results')
def get_ai_results():
    """Return the final AI Top 10 Stock Selection JSON results."""
    with _ai_lock:
        if _ai_progress['running']:
            return jsonify({'error': 'AI Ranking still in progress'}), 202
        return jsonify(_ai_results_store)
