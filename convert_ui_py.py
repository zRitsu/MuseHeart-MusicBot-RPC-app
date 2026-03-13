import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
GUI_DIR = BASE_DIR / "gui"
OUTPUT_DIR = BASE_DIR / "ui"
RES_DIR = GUI_DIR / "res"

OUTPUT_DIR.mkdir(exist_ok=True)

# Compilar recursos (se existir)
qrc_file = RES_DIR / "res.qrc"
if qrc_file.exists():
    subprocess.run([
        "pyrcc5",
        str(qrc_file),
        "-o", str(OUTPUT_DIR / "res_rc.py")
    ], check=True)

# Compilar .ui → .py
for ui_file in GUI_DIR.glob("*.ui"):
    output_py = OUTPUT_DIR / f"{ui_file.stem}.py"

    result = subprocess.run([
        "pyuic5",
        str(ui_file),
        "-o", str(output_py)
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Converted {ui_file.name} → {output_py.name}")

        # Correção de import (se necessário)
        with open(output_py, "r", encoding="utf-8") as f:
            content = f.read()
        if "import res_rc" in content:
            content = content.replace("import res_rc", "from . import res_rc")
            with open(output_py, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  → Fixed relative import")
    else:
        print(f"Erro ao converter {ui_file.name}:")
        print(result.stderr)
