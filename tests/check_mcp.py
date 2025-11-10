import inspect
from mcp.server import Server

s = Server('test')
print('Methods:')
for name in dir(s):
    if not name.startswith('_'):
        attr = getattr(s, name)
        if callable(attr):
            print(f'  - {name}')

