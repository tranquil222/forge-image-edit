"""Sequential variations with one source snapshot and no concurrent inference."""

import traceback

from .workflow import parse_seed


def validate_count(value):
    try:
        count = int(value)
        if isinstance(value, bool) or float(value) != count or not 1 <= count <= 64:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Batch count must be a whole number between 1 and 64.") from None
    return count


def run_batch(generate, args, count, state):
    """Called once on Forge's main thread, inside its normal GPU queue lock.

    Keep only paths and the last image in memory. Every item is saved by the
    native editor before the next starts; an interruption never loses those.
    """
    count = validate_count(count)
    initial_seed = parse_seed(args[7])
    items, output, message = [], None, ""
    state.job_count = count
    for index in range(count):
        if state.interrupted or state.skipped:
            message = "Cancelled."
            break
        state.job_no = index
        state.sampling_step = 0
        state.textinfo = f"Image Edit {index + 1} / {count}"
        call_args = list(args)
        call_args[7] = str(-1 if initial_seed == -1 else (initial_seed + index) % (2**64))
        try:
            image, path, seed, note = generate(*call_args)
        except Exception as error:
            traceback.print_exc()
            message = f"Stopped at edit {index + 1}: {type(error).__name__}: {error}"
            break
        if image is None or path is None:
            message = note
            break
        output = image
        items.append({"path": str(path), "seed": str(seed), "message": note})
        state.job_no = index + 1
        state.sampling_step = 0
        message = note if count == 1 else f"Saved {len(items)} / {count} edits. Select a thumbnail to review or reuse its seed."
    if len(items) < count:
        message += f" {len(items)} / {count} completed edits kept."
    return output, items, message
