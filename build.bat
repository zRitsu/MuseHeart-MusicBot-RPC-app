if not exist venv (
  py -3 -m venv venv
  call "venv\scripts\activate"
  pip install -r requirements.txt
) else (
  call "venv\scripts\activate"
)

::pyinstaller -F -i icon.ico -c --noconsole rpc_client.py
pyinstaller -F -i icon.ico -c rpc_client.py
pause