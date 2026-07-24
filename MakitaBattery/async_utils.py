import threading
import queue


def run_async(widget, work, on_success, on_error=None, poll_ms=30):
    """Run `work` (a zero-arg callable) on a background thread so it can block
    (e.g. on serial I/O) without freezing the Tk UI, then deliver its result
    or exception back on the Tk main thread via `widget.after`.

    `work` must not touch any Tkinter widget — it should only return a plain
    value or raise. All UI updates belong in `on_success`/`on_error`, which
    run on the main thread once `work` finishes.
    """
    result_queue = queue.Queue(maxsize=1)

    def _worker():
        try:
            result_queue.put(("ok", work()))
        except Exception as e:
            result_queue.put(("err", e))

    threading.Thread(target=_worker, daemon=True).start()

    def _poll():
        try:
            status, payload = result_queue.get_nowait()
        except queue.Empty:
            widget.after(poll_ms, _poll)
            return
        if status == "ok":
            on_success(payload)
        elif on_error:
            on_error(payload)
        else:
            raise payload

    widget.after(poll_ms, _poll)
