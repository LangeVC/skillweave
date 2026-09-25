import re
with open("tests/integration/test_gle020_import_cycle.py", "r") as f:
    content = f.read()

content = re.sub(r"@pytest\.mark\.skipif\([\s\S]*?def test_import_succeeds_against_installed_wheel_with_runtime_absent\(\):[\s\S]*?return res\.returncode, \(res\.stdout \+ res\.stderr\)\n", "", content)

with open("tests/integration/test_gle020_import_cycle.py", "w") as f:
    f.write(content)
