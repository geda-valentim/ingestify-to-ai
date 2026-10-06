"""Regression checks for dependency lines that must never be silently skipped."""
import tempfile
from pathlib import Path
from audit_python import lock_pins

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / 'requirements.lock'
    path.write_text('packaging==25.0\n  urllib3==1.26.0\n')
    assert lock_pins(path) == ['packaging==25.0', 'urllib3==1.26.0']
    for directive in ('--requirement hidden.lock', '-r hidden.lock',
                      '--editable ./package', '--trusted-host example.invalid'):
        path.write_text('packaging==25.0\n' + directive + '\n')
        try:
            lock_pins(path)
        except ValueError:
            pass
        else:
            raise AssertionError('Unsupported dependency directive escaped the gate')
    path.write_text('torch @ https://example.invalid/torch-2.8.0%2Bcpu-cp311-cp311-linux_x86_64.whl\n')
    assert lock_pins(path) == ['torch==2.8.0']
print('Indented packages are audited; includes/editables/unsafe directives fail closed')
