"""Read only bounded tails; slicing after read_text still loads the whole log."""

class RenderResourceError(RuntimeError):
    retryable = False


def resource_failure(returncode, output):
    return returncode < 0 or any(s in output.lower() for s in (
        'memoryerror', 'cannot allocate memory', 'std::bad_alloc',
        'resource temporarily unavailable', 'file size limit exceeded', 'out of memory'))


def log_tail(path, maximum=12000):
    with path.open('rb') as stream:
        stream.seek(0,2)
        stream.seek(max(0,stream.tell()-maximum))
        return stream.read(maximum).decode('utf-8',errors='replace')
